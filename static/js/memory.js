(function () {
    'use strict';

    var shell = document.querySelector('.memory-shell');
    if (!shell) return;

    var form = document.getElementById('memoryForm');
    var query = document.getElementById('memoryQuery');
    var submit = document.getElementById('memorySubmit');
    var counter = document.getElementById('memoryCounter');
    var warning = document.getElementById('memoryWarning');
    var output = document.getElementById('memoryOutput');
    var empty = document.getElementById('memoryEmpty');
    var results = document.getElementById('memoryResults');
    var citations = document.getElementById('memoryCitations');
    var followups = document.getElementById('memoryFollowups');
    var semanticEnabled = shell.dataset.semanticEnabled === 'true';

    function setBusy(busy) {
        submit.disabled = busy;
        query.disabled = busy;
        submit.querySelector('span').textContent = busy ? '正在查找…' : '探索记忆';
        shell.classList.toggle('is-loading', busy);
    }

    function clear(element) {
        while (element.firstChild) element.removeChild(element.firstChild);
    }

    function imageUrl(ticket) {
        return ticket.thumbnail_url || ticket.image_url || '';
    }

    function ticketLabel(ticket) {
        return [ticket.time, ticket.type, ticket.city || ticket.place].filter(Boolean).join(' · ');
    }

    function createTicketCard(ticket) {
        var link = document.createElement('a');
        link.className = 'memory-ticket';
        link.href = '/detail/' + encodeURIComponent(ticket.id);

        var visual = document.createElement('div');
        visual.className = 'memory-ticket-visual';
        var src = imageUrl(ticket);
        if (src) {
            var image = document.createElement('img');
            image.src = src;
            image.alt = ticketLabel(ticket) || '票券图片';
            image.loading = 'lazy';
            visual.appendChild(image);
        } else {
            var fallback = document.createElement('span');
            fallback.textContent = (ticket.type || '票').slice(0, 1);
            visual.appendChild(fallback);
        }

        var body = document.createElement('div');
        body.className = 'memory-ticket-body';
        var meta = document.createElement('p');
        meta.className = 'memory-ticket-meta';
        meta.textContent = ticketLabel(ticket) || '未命名票券';
        var place = document.createElement('h3');
        place.textContent = ticket.place || ticket.platform || '一段被收藏的记忆';
        var score = document.createElement('p');
        score.className = 'memory-ticket-score';
        score.textContent = ticket.match_reason + ' · ' + Math.round((ticket.score || 0) * 100) + '%';
        body.appendChild(meta);
        body.appendChild(place);
        body.appendChild(score);
        link.appendChild(visual);
        link.appendChild(body);
        return link;
    }

    function render(data) {
        document.getElementById('memoryAnswerTitle').textContent = data.answer.title || '个人记忆';
        document.getElementById('memoryAnswerText').textContent = data.answer.answer || '';
        document.getElementById('memoryAnswerMode').textContent = data.mode === 'rag' ? 'AI 有据生成' : '本地可解释摘要';
        document.getElementById('memoryMode').lastElementChild.textContent = data.search_mode === 'hybrid' ? '百炼图文语义模式' : '本地关键词模式';
        warning.textContent = data.warning || '';

        clear(results);
        (data.results || []).forEach(function (ticket) {
            results.appendChild(createTicketCard(ticket));
        });
        document.getElementById('memoryResultCount').textContent = (data.results || []).length + ' 张匹配';

        clear(citations);
        if ((data.answer.citations || []).length) {
            var label = document.createElement('span');
            label.textContent = '引用票券';
            citations.appendChild(label);
            data.answer.citations.forEach(function (id) {
                var link = document.createElement('a');
                link.href = '/detail/' + encodeURIComponent(id);
                link.textContent = '#' + id;
                citations.appendChild(link);
            });
        }

        clear(followups);
        (data.answer.follow_up_questions || []).forEach(function (text) {
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = text;
            button.addEventListener('click', function () {
                query.value = text;
                counter.textContent = query.value.length + ' / 300';
                form.requestSubmit();
            });
            followups.appendChild(button);
        });

        empty.hidden = true;
        output.hidden = false;
        output.scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    async function ask(question) {
        setBusy(true);
        warning.textContent = '';
        try {
            var response = await fetch('/api/memory/query', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({query: question})
            });
            var data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || '记忆检索失败');
            render(data);
        } catch (error) {
            warning.textContent = error.message || '记忆检索失败，请稍后重试。';
        } finally {
            setBusy(false);
        }
    }

    query.addEventListener('input', function () {
        counter.textContent = query.value.length + ' / 300';
    });

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        var value = query.value.trim();
        if (value) ask(value);
    });

    document.querySelectorAll('[data-memory-example]').forEach(function (button) {
        button.addEventListener('click', function () {
            query.value = button.dataset.memoryExample;
            counter.textContent = query.value.length + ' / 300';
            query.focus();
        });
    });

    var reindex = document.getElementById('memoryReindex');
    if (reindex && semanticEnabled) {
        reindex.addEventListener('click', async function () {
            reindex.disabled = true;
            reindex.textContent = '正在建立索引…';
            warning.textContent = '百炼会逐张融合票券图片与文字，请保持页面开启。';
            try {
                var response = await fetch('/api/semantic/reindex', {method: 'POST'});
                var data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.message || '索引更新失败');
                warning.textContent = '索引更新完成：处理 ' + data.data.indexed + ' 张票券。';
            } catch (error) {
                warning.textContent = error.message || '索引更新失败，请稍后重试。';
            } finally {
                reindex.disabled = false;
                reindex.textContent = '重建图文索引';
            }
        });
    }
})();
