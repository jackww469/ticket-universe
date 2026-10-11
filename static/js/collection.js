(function () {
    var list = document.getElementById('trashList'), status = document.getElementById('trashStatus');
    async function api(url, options) {
        var response = await fetch(url, options), result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.message || '请求失败');
        return result;
    }
    async function load() {
        status.textContent = '正在加载…';
        try {
            var result = await api('/api/trash');
            list.replaceChildren();
            result.data.forEach(function (ticket) {
                var card = document.createElement('article'); card.className = 'collection-trash-card';
                if (ticket.thumbnail_url) { var image = document.createElement('img'); image.src = ticket.thumbnail_url; image.alt = '票据缩略图'; image.loading = 'lazy'; card.appendChild(image); }
                var title = document.createElement('h3'); title.textContent = ticket.type + ' · ' + ticket.time; card.appendChild(title);
                var info = document.createElement('p'); info.textContent = (ticket.place || '未填写地点') + ' · ' + (ticket.can_restore ? '可恢复至 ' + ticket.expires_at + ' UTC' : '已超过恢复期限'); card.appendChild(info);
                [['恢复', '/restore', 'POST'], ['永久删除', '', 'DELETE']].forEach(function (action) {
                    var button = document.createElement('button'); button.className = 'btn btn-ghost'; button.textContent = action[0];
                    button.disabled = action[2] === 'POST' && !ticket.can_restore;
                    button.onclick = async function () {
                        if (action[2] === 'DELETE' && !confirm('永久删除这张票据和图片？此操作无法撤销。')) return;
                        button.disabled = true;
                        try { await api('/api/trash/' + ticket.id + action[1], {method: action[2]}); await load(); }
                        catch (error) { status.textContent = error.message; button.disabled = false; }
                    };
                    card.appendChild(button);
                });
                list.appendChild(card);
            });
            status.textContent = result.data.length ? '共 ' + result.data.length + ' 张票据' : '回收站为空';
        } catch (error) { status.textContent = error.message + '，请点击刷新重试'; }
    }
    document.getElementById('refreshTrash').onclick = load;
    document.getElementById('restoreBackup').onsubmit = async function (event) {
        event.preventDefault();
        var form = event.currentTarget, button = form.querySelector('button'), message = document.getElementById('backupStatus');
        button.disabled = true; message.textContent = '正在校验并恢复，请勿关闭页面…';
        try { var result = await api('/api/backup/import', {method: 'POST', body: new FormData(form)}); message.textContent = result.message; }
        catch (error) { message.textContent = error.message; }
        finally { button.disabled = false; }
    };
    load();
})();
