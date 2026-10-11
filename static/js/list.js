/**
 * 我的票夹：分类筛选、关键词搜索、新版卡片渲染
 */
(function () {
    var filterBtns = document.getElementById('filterBtns');
    var searchInput = document.getElementById('searchInput');
    var searchClearBtn = document.getElementById('searchClearBtn');
    var cardGrid = document.getElementById('cardGrid');
    var listLoading = document.getElementById('listLoading');
    var emptyState = document.getElementById('emptyState');
    var emptyDesc = document.getElementById('emptyDesc');
    var walletCount = document.getElementById('walletCount');

    var currentType = '全部';
    var searchKeyword = '';
    var allData = [];
    var page = 1, pages = 0, requestId = 0;
    var filters = document.getElementById('advancedFilters');
    var listStatus = document.getElementById('listStatus');

    function esc(s) {
        if (s == null) return '';
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML.replace(/"/g, '&quot;');
    }

    function setLoading(loading) {
        if (!listLoading) return;
        listLoading.style.display = loading ? 'flex' : 'none';
        if (emptyState) emptyState.hidden = true;
    }

    function updateCount(n) {
        if (walletCount) walletCount.textContent = n || 0;
    }

    function renderCards(data) {
        // 移除之前的所有卡片
        cardGrid.querySelectorAll('.wallet-card').forEach(function (n) { n.remove(); });
        if (emptyState) emptyState.hidden = true;

        if (!data || !data.length) {

            if (emptyDesc) {
                emptyDesc.innerHTML = searchKeyword
                    ? '没有匹配的票据，试试其他关键词'
                    : '还没有收藏任何票据，<a href="/upload">去上传第一张</a>';
            }
            if (emptyState) emptyState.hidden = false;
            return;
        }



        var frag = document.createDocumentFragment();
        data.forEach(function (item) {
            frag.appendChild(buildCard(item));
        });
        cardGrid.appendChild(frag);
    }

    function buildCard(item) {
        var card = document.createElement('a');
        card.href = '/detail/' + item.id;
        card.className = 'wallet-card' + (item.type === '证书' ? ' is-cert' : '');

        // 主题色侧条
        var tc = (item.theme_color || '').trim();
        if (/^#[0-9A-Fa-f]{3,8}$/.test(tc)) {
            card.style.setProperty('--card-theme', tc);
        }

        // 类型徽章
        var typeText = esc(item.type || '其他');
        var badge = '<span class="wallet-card-badge type-' + esc(item.type || '其他') + '">' + typeText + '</span>';

        // 缩略图
        var imgSrc = item.thumbnail_url || item.image_url || '';
        var thumbHtml = imgSrc
            ? '<img src="' + esc(imgSrc) + '" alt="" loading="lazy">'
            : '<div class="wallet-card-thumb-empty" aria-hidden="true">' +
              '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
              '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M21 17l-5-5-9 9"/>' +
              '</svg></div>';
        var thumb = '<div class="wallet-card-thumb">' + badge + thumbHtml + '</div>';

        // 元信息行（日期 + 平台）
        var metaRow = '<div class="wallet-card-meta-row">' +
            '<span class="wallet-card-date">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>' +
            esc(item.time || '--') +
            '</span>' +
            (item.platform ? '<span class="wallet-card-platform">' + esc(item.platform) + '</span>' : '') +
            '</div>';

        // 地点
        var place = esc(item.place || '未填写地点');

        // 备注
        var notes = item.notes
            ? '<p class="wallet-card-notes">' + esc(item.notes) + '</p>'
            : '';

        // 底部（主题色 + 类型计数）
        var themeSwatch = tc
            ? '<span class="wallet-card-theme"><span class="wallet-card-theme-swatch" style="background:' + esc(tc) + '"></span>主题色</span>'
            : '<span class="wallet-card-theme">¥ 收藏纪念</span>';

        var foot = '<div class="wallet-card-foot">' +
            themeSwatch +
            '<span>查看详情 →</span>' +
            '</div>';

        card.innerHTML = thumb +
            '<div class="wallet-card-body">' +
            metaRow +
            '<div class="wallet-card-place">' + place + '</div>' +
            notes +
            foot +
            '</div>';

        return card;
    }

    function loadList() {
        var activeRequest = ++requestId;
        setLoading(true);
        listStatus.textContent = '';
        var params = new URLSearchParams(new FormData(filters));
        params.set('type', currentType); params.set('q', searchKeyword); params.set('page', page); params.set('per_page', 24);
        document.getElementById('prevPage').disabled = true;
        document.getElementById('nextPage').disabled = true;
        fetch('/api/tickets?' + params.toString())
            .then(function (r) { return r.json().then(function (res) { if (!r.ok || !res.success) throw new Error(res.message || '加载失败'); return res; }); })
            .then(function (res) {
                if (activeRequest !== requestId) return;
                setLoading(false);
                allData = res.data || []; pages = res.pages || 0;
                if (page > pages && pages > 0) { page = pages; loadList(); return; }
                updateCount(res.total); renderCards(allData);
                document.getElementById('pageInfo').textContent = pages ? page + ' / ' + pages + ' 页' : '暂无结果';
                document.getElementById('prevPage').disabled = page <= 1;
                document.getElementById('nextPage').disabled = page >= pages;
                history.replaceState(null, '', '/list?' + params.toString());
            }).catch(function (error) {
                if (activeRequest !== requestId) return;
                setLoading(false);
                listStatus.textContent = error.message + '，请重新筛选重试。';
            });
    }
    filters.addEventListener('submit', function (event) { event.preventDefault(); page = 1; searchKeyword = searchInput.value.trim(); loadList(); });
    filters.addEventListener('reset', function () { setTimeout(function () { page = 1; loadList(); }, 0); });
    document.getElementById('prevPage').onclick = function () { if (page > 1) { page--; loadList(); } };
    document.getElementById('nextPage').onclick = function () { if (page < pages) { page++; loadList(); } };

    function doSearch() {
        page = 1;
        searchKeyword = searchInput ? searchInput.value.trim() : '';
        toggleClear();
        loadList();
    }

    function toggleClear() {
        if (!searchClearBtn) return;
        var has = !!(searchInput && searchInput.value.trim());
        var wrap = document.querySelector('.wallet-search');
        if (wrap) wrap.classList.toggle('has-value', has);
    }

    if (filterBtns) {
        filterBtns.addEventListener('click', function (e) {
            var btn = e.target.closest('.wallet-tab');
            if (!btn) return;
            filterBtns.querySelectorAll('.wallet-tab').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            currentType = btn.getAttribute('data-type') || '全部';
            page = 1;
            searchKeyword = searchInput.value.trim();
            toggleClear();
            loadList();
        });
    }

    if (searchInput) {
        searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') doSearch();
        });
        searchInput.addEventListener('input', toggleClear);
    }

    if (searchClearBtn) {
        searchClearBtn.addEventListener('click', function () {
            if (searchInput) searchInput.value = '';
            searchKeyword = '';
            page = 1;
            toggleClear();
            loadList();
            if (searchInput) searchInput.focus();
        });
    }

    // 初始：根据 URL 参数设置筛选
    var params = new URLSearchParams(window.location.search);
    var typeParam = params.get('type');
    var qParam = params.get('q');
    ['date_from', 'date_to', 'province', 'city', 'platform'].forEach(function (key) { filters.elements[key].value = params.get(key) || ''; });
    page = Math.max(1, parseInt(params.get('page'), 10) || 1);
    if (typeParam && filterBtns) {
        currentType = typeParam;
        var activeBtn = Array.from(filterBtns.querySelectorAll('[data-type]')).find(function (b) { return b.getAttribute('data-type') === typeParam; });
        if (activeBtn) {
            filterBtns.querySelectorAll('.wallet-tab').forEach(function (b) { b.classList.remove('active'); });
            activeBtn.classList.add('active');
        }
    }
    if (qParam) {
        searchKeyword = qParam;
        if (searchInput) searchInput.value = qParam;
    }
    toggleClear();
    loadList();
})();