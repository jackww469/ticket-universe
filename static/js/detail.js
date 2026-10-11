/**
 * 详情页：加载票据、编辑、删除
 * 博物馆风格详情页
 */
(function () {
    var id = window.TICKET_ID;
    var detailWrap = document.getElementById('detailWrap');
    var detailLoading = document.getElementById('detailLoading');
    var detailContent = document.getElementById('detailContent');
    var detailError = document.getElementById('detailError');
    var editModal = document.getElementById('editModal');
    var editForm = document.getElementById('editForm');
    var notesModal = document.getElementById('notesModal');

    // Ticket mockup elements
    var ticketGradient = document.getElementById('ticketGradient');
    var ticketEventName = document.getElementById('ticketEventName');
    var ticketCategory = document.getElementById('ticketCategory');
    var ticketDate = document.getElementById('ticketDate');
    var ticketVenue = document.getElementById('ticketVenue');
    var ticketTourLabel = document.getElementById('ticketTourLabel');
    var stubEventName = document.getElementById('stubEventName');
    var stubCategory = document.getElementById('stubCategory');
    var stubDatetime = document.getElementById('stubDatetime');
    var seatEntrance = document.getElementById('seatEntrance');
    var seatSection = document.getElementById('seatSection');
    var seatRow = document.getElementById('seatRow');
    var seatSeat = document.getElementById('seatSeat');

    function escapeHtml(s) {
        if (s == null) return '';
        var div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function formatDateForDisplay(dateStr) {
        if (!dateStr) return '';
        var d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        var months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
        var day = d.getDate();
        var month = months[d.getMonth()];
        var year = d.getFullYear();
        return day + ' ' + month + ' ' + year;
    }

    function formatDateForInput(dateStr) {
        if (!dateStr) return '';
        return dateStr.slice(0, 10);
    }

    function updateTicketMockup(data) {
        // Update ticket gradient with theme color
        if (data.theme_color && /^#[0-9A-Fa-f]{3,8}$/.test(data.theme_color)) {
            var tc = data.theme_color;
            // Generate gradient from theme color
            ticketGradient.style.background = `linear-gradient(135deg, ${tc} 0%, ${adjustColor(tc, 20)} 50%, ${adjustColor(tc, 40)} 100%)`;
        }

        // Extract text from place for venue
        var placeText = data.place || 'Music Arena';
        ticketVenue.textContent = placeText;

        // Format date for ticket
        var dateText = formatDateForDisplay(data.time ? data.time.slice(0, 10) : null);
        if (dateText) {
            ticketDate.textContent = dateText + ' | 20:00';
        } else {
            ticketDate.textContent = 'TBD';
        }

        // Update stub
        stubDatetime.textContent = ticketDate.textContent;

        // Update event name based on type
        var typeText = data.type || 'EVENT';
        ticketEventName.textContent = typeText.toUpperCase();
        stubEventName.textContent = typeText.toUpperCase();

        // Update category based on platform
        var platformText = data.platform || 'GENERAL';
        ticketCategory.textContent = platformText.toUpperCase();
        stubCategory.textContent = platformText.toUpperCase();

        // Tour label based on type
        var tourLabel = 'EVENT';
        if (data.type && (data.type.includes('演出') || data.type.includes('concert'))) {
            tourLabel = 'WORLD TOUR';
        } else if (data.type && (data.type.includes('景区') || data.type.includes('景区'))) {
            tourLabel = 'SCENIC SPOT';
        } else if (data.type && (data.type.includes('车票') || data.type.includes('火车'))) {
            tourLabel = 'TRANSIT';
        } else if (data.type && data.type.includes('证书')) {
            tourLabel = 'CERTIFICATE';
        }
        ticketTourLabel.textContent = tourLabel;
    }

    function adjustColor(hex, percent) {
        var num = parseInt(hex.replace('#', ''), 16);
        var amt = Math.round(2.55 * percent);
        var R = (num >> 16) + amt;
        var G = (num >> 8 & 0x00FF) + amt;
        var B = (num & 0x0000FF) + amt;
        return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
    }

    function showContent(data) {
        // Update ticket mockup
        updateTicketMockup(data);

        // Show/hide image
        var imageWrap = document.getElementById('ticketImageWrap');
        var noImageEl = document.getElementById('detailNoImage');
        var ticketMockup = document.getElementById('ticketMockup');

        if (data.image_url) {
            document.getElementById('detailImage').src = data.image_url;
            imageWrap.style.display = 'block';
            ticketMockup.style.display = 'none';
            if (noImageEl) noImageEl.style.display = 'none';
        } else {
            imageWrap.style.display = 'none';
            ticketMockup.style.display = 'block';
            if (noImageEl) noImageEl.style.display = 'none';
        }

        // Update detail meta
        var typeText = data.type || '—';
        document.getElementById('detailType').textContent = typeText;
        document.getElementById('detailPlatform').textContent = data.platform || '—';
        document.getElementById('detailTime').textContent = data.time ? data.time.slice(0, 10) : '—';
        document.getElementById('detailPlace').textContent = data.place || '—';

        // Province/City row
        var provinceCityRow = document.getElementById('provinceCityRow');
        if (data.province || data.city) {
            provinceCityRow.style.display = 'flex';
            document.getElementById('detailProvince').textContent = data.province || '';
            document.getElementById('detailCityText').textContent = (data.province && data.city) ? ' / ' + data.city : (data.city || '');
        } else {
            provinceCityRow.style.display = 'none';
        }

        // Notes
        var notesText = data.notes && data.notes.trim() ? data.notes : null;
        var detailNotes = document.getElementById('detailNotes');
        if (notesText) {
            detailNotes.textContent = notesText;
            detailNotes.classList.remove('meta-value--placeholder');
        } else {
            detailNotes.textContent = '—';
            detailNotes.classList.add('meta-value--placeholder');
        }

        // OCR text
        var ocrText = data.ocr_text && data.ocr_text.trim() ? data.ocr_text : null;
        var detailOcr = document.getElementById('detailOcr');
        if (ocrText) {
            detailOcr.textContent = ocrText;
            detailOcr.classList.remove('meta-value--placeholder');
        } else {
            detailOcr.textContent = '—';
            detailOcr.classList.add('meta-value--placeholder');
        }

        // OCR text in box
        var ocrBox = document.getElementById('ocrText');
        if (ocrText) {
            ocrBox.textContent = ocrText;
        } else {
            ocrBox.textContent = '暂无 OCR 识别内容';
        }

        // Notes in box
        var notesPlaceholder = document.getElementById('notesPlaceholder');
        var notesTextEl = document.getElementById('notesText');
        if (notesText) {
            notesPlaceholder.style.display = 'none';
            notesTextEl.style.display = 'block';
            notesTextEl.textContent = notesText;
        } else {
            notesPlaceholder.style.display = 'block';
            notesTextEl.style.display = 'none';
            notesTextEl.textContent = '';
        }

        // Theme color
        var themeEl = document.getElementById('detailTheme');
        if (themeEl) {
            themeEl.innerHTML = '';
            var tc = (data.theme_color || '').trim();
            if (!tc) {
                themeEl.innerHTML = '<span class="meta-value--placeholder">—</span>';
            } else if (/^#[0-9A-Fa-f]{3,8}$/.test(tc)) {
                var sw = document.createElement('span');
                sw.className = 'theme-inline-swatch';
                sw.style.background = tc;
                themeEl.appendChild(sw);
                var hex = document.createElement('span');
                hex.className = 'theme-color-hex';
                hex.textContent = tc.toUpperCase();
                themeEl.appendChild(hex);
            } else {
                themeEl.textContent = tc;
            }
        }

        // Type badge
        var badgeTypeText = document.getElementById('badgeTypeText');
        if (badgeTypeText) {
            badgeTypeText.textContent = typeText;
        }

        // Apply theme color to ticket mockup
        if (data.theme_color && ticketGradient) {
            ticketGradient.style.background = `linear-gradient(135deg, ${data.theme_color} 0%, ${adjustColor(data.theme_color, 20)} 50%, ${adjustColor(data.theme_color, 40)} 100%)`;
        }

        // Update edit link
        document.getElementById('editLink').href = '#edit';

        // Hide loading, show content
        detailLoading.style.display = 'none';
        detailError.style.display = 'none';
        detailContent.style.display = 'flex';
    }

    function showErr() {
        detailLoading.style.display = 'none';
        detailContent.style.display = 'none';
        detailError.style.display = 'flex';
    }

    // Fetch and display ticket
    function loadTicket() {
        fetch('/api/tickets/' + id)
            .then(function (r) {
                if (!r.ok) throw new Error('404');
                return r.json();
            })
            .then(function (res) {
                if (res.success && res.data) {
                    showContent(res.data);
                } else {
                    showErr();
                }
            })
            .catch(function () {
                showErr();
            });
    }

    loadTicket();

    // Edit button
    document.getElementById('editLink').addEventListener('click', function (e) {
        e.preventDefault();
        fetch('/api/tickets/' + id)
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res.success && res.data) {
                    var d = res.data;
                    document.getElementById('editId').value = id;
                    document.getElementById('editType').value = d.type || '';
                    document.getElementById('editPlatform').value = d.platform || '';
                    document.getElementById('editTime').value = formatDateForInput(d.time);
                    document.getElementById('editNotes').value = d.notes || '';
                    document.getElementById('editPlace').value = d.place || '';
                    document.getElementById('editProvince').value = d.province || '';
                    document.getElementById('editCity').value = d.city || '';
                    document.getElementById('editOcrText').value = d.ocr_text || '';
                    document.getElementById('editThemeColor').value = d.theme_color || '';
                    document.getElementById('editImage').value = '';
                    editModal.style.display = 'flex';
                }
            });
    });

    // Edit modal close
    var editModalClose = document.getElementById('editModalClose');
    var editModalClose2 = document.getElementById('editModalClose2');

    editModalClose.addEventListener('click', function () {
        editModal.style.display = 'none';
    });

    if (editModalClose2) {
        editModalClose2.addEventListener('click', function () {
            editModal.style.display = 'none';
        });
    }

    editModal.addEventListener('click', function (e) {
        if (e.target === editModal) editModal.style.display = 'none';
    });

    // Edit form submit
    editForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var fd = new FormData(editForm);
        fd.delete('id');
        var xhr = new XMLHttpRequest();
        xhr.open('PUT', '/api/tickets/' + id);
        xhr.onload = function () {
            var res;
            try {
                res = JSON.parse(xhr.responseText);
            } catch (err) {
                showToast('更新失败');
                return;
            }
            if (res.success) {
                showToast('更新成功');
                editModal.style.display = 'none';
                loadTicket();
            } else {
                showToast(res.message || '更新失败');
            }
        };
        xhr.send(fd);
    });

    // Delete button
    document.getElementById('deleteBtn').addEventListener('click', function () {
        if (!confirm('将这张票据移入回收站？30 天内可恢复。')) return;
        fetch('/api/tickets/' + id, { method: 'DELETE' })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res.success) {
                    showToast('已移入回收站，30 天内可恢复');
                    setTimeout(function () {
                        window.location.href = '/list';
                    }, 800);
                } else {
                    showToast(res.message || '删除失败');
                }
            });
    });

    // Copy OCR button
    document.getElementById('copyOcrBtn').addEventListener('click', function () {
        var ocrText = document.getElementById('ocrText').textContent;
        if (ocrText && ocrText !== '暂无 OCR 识别内容') {
            navigator.clipboard.writeText(ocrText).then(function () {
                showToast('已复制到剪贴板');
            }).catch(function () {
                showToast('复制失败');
            });
        } else {
            showToast('暂无内容可复制');
        }
    });

    // Quick notes modal
    var quickNotesText = document.getElementById('quickNotesText');
    var notesModalClose = document.getElementById('notesModalClose');
    var notesModalCancel = document.getElementById('notesModalCancel');
    var notesModalSave = document.getElementById('notesModalSave');
    var notesContent = document.getElementById('notesContent');
    var editNotesBtn = document.getElementById('editNotesBtn');

    function openNotesModal() {
        // Get current notes from the display
        var notesTextEl = document.getElementById('notesText');
        var currentNotes = notesTextEl.style.display !== 'none' ? notesTextEl.textContent : '';
        quickNotesText.value = currentNotes;
        notesModal.style.display = 'flex';
        quickNotesText.focus();
    }

    if (editNotesBtn) {
        editNotesBtn.addEventListener('click', openNotesModal);
    }

    if (notesContent) {
        notesContent.addEventListener('click', openNotesModal);
    }

    if (notesModalClose) {
        notesModalClose.addEventListener('click', function () {
            notesModal.style.display = 'none';
        });
    }

    if (notesModalCancel) {
        notesModalCancel.addEventListener('click', function () {
            notesModal.style.display = 'none';
        });
    }

    notesModal.addEventListener('click', function (e) {
        if (e.target === notesModal) notesModal.style.display = 'none';
    });

    if (notesModalSave) {
        notesModalSave.addEventListener('click', function () {
            var newNotes = quickNotesText.value.trim();

            // Save via API
            var fd = new FormData();
            fd.append('notes', newNotes);

            var xhr = new XMLHttpRequest();
            xhr.open('PUT', '/api/tickets/' + id);
            xhr.setRequestHeader('X-HTTP-Method-Override', 'PATCH');
            xhr.onload = function () {
                try {
                    var res = JSON.parse(xhr.responseText);
                    if (res.success) {
                        showToast('备注已更新');
                        notesModal.style.display = 'none';
                        loadTicket();
                    } else {
                        showToast(res.message || '更新失败');
                    }
                } catch (err) {
                    showToast('更新失败');
                }
            };
            xhr.onerror = function () {
                showToast('更新失败');
            };
            xhr.send(fd);
        });
    }

    // More button dropdown (simple implementation)
    var moreBtn = document.getElementById('moreBtn');
    if (moreBtn) {
        moreBtn.addEventListener('click', function (e) {
            // For now, just open edit modal
            document.getElementById('editLink').click();
        });
    }
})();
