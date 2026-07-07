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
        .then(function (r) { return r.json(); })
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
            }
        })
        .catch(function () {});
})();

/**
 * 天气小部件 - 更新为新样式
 */
(function () {
    function updateWeatherWidget(data) {
        if (!data || !data.current_condition) return;

        var current = data.current_condition[0];
        var temp = current.temp_C + '°C';
        var weatherCode = parseInt(current.weatherCode);
        var desc = current.weatherDesc[0].value;
        var minTemp = data.weather[0].mintempC;
        var maxTemp = data.weather[0].maxtempC;

        // 更新天气信息
        var tempEl = document.querySelector('.weather-widget .text-4xl');
        var descEl = document.querySelector('.weather-widget .text-lg');
        var rangeEl = document.querySelector('.weather-widget .text-sm.text-gray-400');

        if (tempEl) tempEl.innerHTML = temp + ' <span class="text-lg font-normal text-gray-400 ml-1">' + desc + '</span>';
        if (rangeEl) rangeEl.textContent = minTemp + '°C ~ ' + maxTemp + '°C · 空气优';
    }

    function fetchWeather() {
        // 默认显示北京天气
        var url = 'https://wttr.in/Beijing?format=j1';
        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                updateWeatherWidget(data);
            })
            .catch(function () {});
    }

    fetchWeather();
})();
