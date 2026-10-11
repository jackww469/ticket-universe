(function () {
    var form = document.getElementById('uploadForm');
    var input = document.getElementById('image');
    var select = document.getElementById('uploadQueue');
    var preview = document.getElementById('previewImg');
    var status = document.getElementById('uploadStatus');
    var submit = document.getElementById('uploadSubmit');
    var ocr = document.getElementById('ocrBtn');
    var dialog = document.getElementById('ocrReview');
    var review = document.getElementById('ocrFields');
    var queue = [], active = -1, busy = false, previewUrl, reviewItem;
    var keys = ['type', 'platform', 'time', 'place', 'province', 'city', 'notes', 'ocr_text', 'theme_color'];
    var labels = {type: '类型', time: '日期', place: '地点', province: '省份', city: '城市', ocr_text: '识别全文', theme_color: '主题色'};
    bindLocationInputs('province', 'city');
    function snapshot() {
        if (active < 0 || !queue[active]) return;
        keys.forEach(function (key) { queue[active].fields[key] = document.getElementById(key).value; });
    }
    function renderQueue() {
        select.replaceChildren();
        queue.forEach(function (item, index) {
            var option = document.createElement('option'); option.value = index;
            option.textContent = (index + 1) + '. ' + item.file.name + ' — ' + item.status;
            select.appendChild(option);
        });
        select.value = active;
    }
    function activate(index) {
        snapshot(); active = index;
        var item = queue[active];
        keys.forEach(function (key) { document.getElementById(key).value = item ? (item.fields[key] || '') : ''; });
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = item ? URL.createObjectURL(item.file) : '';
        preview.src = previewUrl;
        document.getElementById('uploadPreview').style.display = item ? 'block' : 'none';
        document.getElementById('uploadPlaceholder').style.display = item ? 'none' : 'block';
        renderQueue();
    }
    function addFiles(files) {
        if (busy) return;
        snapshot();
        Array.from(files).forEach(function (file) {
            if (queue.length >= 20) { showToast('每批最多 20 张图片'); return; }
            if (!file.type.startsWith('image/') || file.size > 5 * 1024 * 1024) { showToast(file.name + '：请选择不超过 5MB 的图片'); return; }
            queue.push({file: file, fields: {}, status: '待编辑', done: false});
        });
        if (active < 0 && queue.length) activate(0); else renderQueue();
        input.value = '';
    }
    var area = document.getElementById('uploadArea');
    area.onclick = function (event) { if (!busy && event.target !== document.getElementById('previewRemove') && event.target !== input) input.click(); };
    area.ondragover = function (event) { event.preventDefault(); };
    area.ondrop = function (event) { event.preventDefault(); addFiles(event.dataTransfer.files); };
    input.onchange = function () { addFiles(input.files); };
    select.onchange = function () { if (!busy) activate(Number(select.value)); };
    document.getElementById('previewRemove').onclick = function (event) {
        event.stopPropagation(); if (busy || active < 0) return;
        queue.splice(active, 1); active = -1; activate(queue.length ? 0 : -1);
    };
    document.getElementById('copyBatchFields').onclick = function () {
        if (busy || active < 0) return;
        snapshot();
        var current = queue[active].fields;
        queue.forEach(function (item) { if (!item.done) ['type', 'time', 'platform', 'province', 'city'].forEach(function (key) { item.fields[key] = current[key]; }); });
        showToast('已应用到尚未上传的图片');
    };
    function setBusy(value) {
        busy = value;
        form.querySelectorAll('input, textarea, select, button').forEach(function (node) { node.disabled = value; });
    }
    function renderReview(item) {
        reviewItem = item; review.replaceChildren();
        Object.keys(labels).forEach(function (key) {
            var proposed = key === 'ocr_text' ? item.ocr.raw_text : item.ocr[key];
            if (!proposed) return;
            var label = document.createElement('label'); label.className = 'ocr-review-field';
            var checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.dataset.key = key;
            checkbox.checked = !(item.fields[key] || '').trim(); checkbox.value = proposed;
            label.append(checkbox, document.createTextNode(' ' + labels[key] + '\n当前：' + (item.fields[key] || '空白') + '\n建议：' + proposed));
            review.appendChild(label);
        });
        var places = document.getElementById('ocrLocations'); places.replaceChildren();
        var initial = document.createElement('option'); initial.value = ''; initial.textContent = '保留上方省市选择'; places.appendChild(initial);
        (item.ocr.location_candidates || []).forEach(function (place, index) {
            var option = document.createElement('option'); option.value = index; option.textContent = place.province + ' / ' + place.city; places.appendChild(option);
        });
        document.getElementById('ocrLocationWarning').textContent = item.ocr.location_warning || '';
        dialog.showModal();
    }
    ocr.onclick = async function () {
        if (busy || active < 0) { showToast('请先选择图片'); return; }
        snapshot(); var item = queue[active]; setBusy(true); ocr.textContent = '识别中…';
        try {
            var body = new FormData(); body.append('image', item.file);
            var response = await fetch('/api/ocr/extract', {method: 'POST', body: body});
            var result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.message || '识别失败');
            item.ocr = result.data; renderReview(item);
        } catch (error) { showToast(error.message); }
        finally { setBusy(false); ocr.textContent = '自动识别'; }
    };
    document.getElementById('ocrCancel').onclick = function () { dialog.close(); };
    document.getElementById('ocrApply').onclick = function () {
        review.querySelectorAll('input:checked').forEach(function (checkbox) { reviewItem.fields[checkbox.dataset.key] = checkbox.value; });
        var selected = document.getElementById('ocrLocations').value;
        if (selected !== '') {
            var place = reviewItem.ocr.location_candidates[Number(selected)];
            reviewItem.fields.province = place.province; reviewItem.fields.city = place.city;
        }
        keys.forEach(function (key) { document.getElementById(key).value = reviewItem.fields[key] || ''; });
        var color = reviewItem.fields.theme_color;
        document.getElementById('themeSwatch').style.background = /^#[0-9a-f]{6}$/i.test(color || '') ? color : '#808080';
        document.getElementById('themePreviewLabel').textContent = '主题：' + (reviewItem.ocr.theme_label || '通用票根');
        dialog.close(); showToast('已应用所选字段，请校对后上传');
    };
    form.onsubmit = async function (event) {
        event.preventDefault(); if (busy) return;
        snapshot(); if (!queue.length) { showToast('请先添加图片'); return; }
        var invalid = queue.findIndex(function (item) { return !item.done && (!item.fields.type || !/^\d{4}-\d{2}-\d{2}$/.test(item.fields.time || '')); });
        if (invalid >= 0) { activate(invalid); showToast('请填写这张图片的类型和日期'); return; }
        setBusy(true);
        for (var i = 0; i < queue.length; i++) {
            var item = queue[i]; if (item.done) continue;
            item.status = '上传中'; renderQueue(); status.textContent = '正在上传 ' + (i + 1) + ' / ' + queue.length;
            try {
                var body = new FormData(); keys.forEach(function (key) { body.append(key, item.fields[key] || ''); }); body.append('image', item.file);
                var response = await fetch('/api/tickets', {method: 'POST', body: body}); var result = await response.json();
                if (response.status === 409) {
                    if (!confirm(item.file.name + '：相同图片已存在' + (result.duplicate.deleted_at ? '于回收站' : '') + '，仍然新增一份？')) { item.status = '重复，未上传'; continue; }
                    body.append('allow_duplicate', '1'); response = await fetch('/api/tickets', {method: 'POST', body: body}); result = await response.json();
                }
                if (!response.ok || !result.success) throw new Error(result.message || '上传失败');
                item.done = true; item.status = '已上传';
            } catch (error) { item.status = error.message; }
            finally { renderQueue(); }
        }
        setBusy(false);
        var completed = queue.filter(function (item) { return item.done; }).length;
        status.textContent = '已上传 ' + completed + ' / ' + queue.length + ' 张。未成功的图片可编辑后重试，已成功的不会重复提交。';
    };
})();
