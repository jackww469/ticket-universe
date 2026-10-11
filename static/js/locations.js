/* Shared editable province/city suggestions for upload, edit and filters. */
(function () {
    var catalog;
    window.locationCatalog = function () {
        if (!catalog) catalog = fetch('/api/locations').then(function (r) {
            if (!r.ok) throw new Error('地点词库加载失败');
            return r.json();
        }).then(function (r) { return r.data; });
        return catalog;
    };
    window.bindLocationInputs = function (provinceId, cityId) {
        var province = document.getElementById(provinceId), city = document.getElementById(cityId);
        if (!province || !city) return;
        var provinceList = document.createElement('datalist'), cityList = document.createElement('datalist');
        provinceList.id = provinceId + 'Options'; cityList.id = cityId + 'Options';
        document.body.append(provinceList, cityList);
        province.setAttribute('list', provinceList.id); city.setAttribute('list', cityList.id);
        window.locationCatalog().then(function (data) {
            function fill(list, values) {
                list.replaceChildren();
                values.forEach(function (value) { var option = document.createElement('option'); option.value = value; list.appendChild(option); });
            }
            fill(provinceList, Object.keys(data));
            function refresh() {
                fill(cityList, data[province.value] || Array.from(new Set(Object.values(data).flat())));
            }
            province.addEventListener('input', refresh);
            province.addEventListener('change', function () {
                province.value = province.value.trim().replace(/(壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区|省|市)$/, '');
                refresh();
            });
            city.addEventListener('change', function () {
                var name = city.value.trim().replace(/市$/, '');
                var matches = Object.keys(data).filter(function (p) { return data[p].includes(name); });
                if (matches.length) city.value = name;
                if (!province.value && matches.length === 1) province.value = matches[0];
                refresh();
            });
            refresh();
        }).catch(function () { /* Keep manual entry usable when suggestions are unavailable. */ });
    };
})();
