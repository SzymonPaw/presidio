/* app.js - frontend dla anonimizatora z podglądem PDF */
(function () {
    'use strict';

    var form = document.getElementById('upload-form');
    var fileInput = document.getElementById('file-input');
    var fileLabel = document.querySelector('.file-label');
    var fileInfo = document.getElementById('file-info');
    var analyzeBtn = document.getElementById('analyze-btn');
    var statusDiv = document.getElementById('status');
    var findingsDiv = document.getElementById('findings');

    // Modal elements
    var modal = document.getElementById('preview-modal');
    var modalCloseBtn = document.querySelector('.close-btn');
    var previewImage = document.getElementById('preview-image');
    var previewPageNumSpan = document.getElementById('preview-page-num');

    var selectedFile = null;

    // Drag and drop
    if (fileLabel) {
        fileLabel.addEventListener('dragover', function (e) {
            e.preventDefault();
            fileLabel.classList.add('dragover');
        });
        fileLabel.addEventListener('dragleave', function () {
            fileLabel.classList.remove('dragover');
        });
        fileLabel.addEventListener('drop', function (e) {
            e.preventDefault();
            fileLabel.classList.remove('dragover');
            var files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });
    }

    // Klikniecie w label
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            if (fileInput.files.length > 0) {
                handleFile(fileInput.files[0]);
            }
        });
    }

    function handleFile(file) {
        selectedFile = file;
        fileInfo.textContent = 'Wybrany plik: ' + file.name + ' (' + formatSize(file.size) + ')';
        analyzeBtn.disabled = false;
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!selectedFile) return;

            statusDiv.textContent = 'Analizowanie...';
            findingsDiv.innerHTML = '';

            var formData = new FormData();
            formData.append('file', selectedFile);

            fetch('/analyze', {
                method: 'POST',
                body: formData
            })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                statusDiv.textContent = '';
                if (data.error) {
                    statusDiv.textContent = 'Błąd: ' + data.error;
                    return;
                }
                renderFindings(data.findings);
            })
            .catch(function (err) {
                statusDiv.textContent = 'Błąd komunikacji z serwerem.';
                console.error(err);
            });
        });
    }

    function renderFindings(findings) {
        if (!findings || findings.length === 0) {
            findingsDiv.innerHTML = '<p>Nie wykryto żadnych danych do anonimizacji.</p>';
            return;
        }

        var isPdf = selectedFile && selectedFile.name.toLowerCase().endswith ?
            selectedFile.name.toLowerCase().endswith('.pdf') :
            /\.pdf$/i.test(selectedFile.name);

        var html = '<h2>Wykryte dane</h2>';
        html += '<table class="findings-table"><thead><tr><th>Typ</th><th>Znacznik</th><th>Siła</th><th>Liczba</th><th>Anonimizuj</th>';
        // html += '<table class="findings-table"><thead><tr><th>Typ</th><th>Znacznik</th><th>Siła</th><th>Powód</th><th>Liczba</th><th>Anonimizuj</th>';
        if (isPdf) {
            html += '<th>Akcje</th>';
        }
        html += '</tr></thead><tbody>';

        findings.forEach(function (f) {
            html += '<tr>';
            html += '<td>' + escapeHtml(f.entity_type) + '</td>';
            html += '<td>' + escapeHtml(f.marker) + '</td>';
            html += '<td>' + f.score.toFixed(2) + '</td>';
            // html += '<td>' + escapeHtml(f.reason) + '</td>';
            html += '<td>' + f.count + '</td>';
            html += '<td><input type="checkbox" name="anonymize" value="' + f.id + '" checked></td>';
            if (isPdf) {
                // Jeśli PDF, dajemy przycisk Pokaż z podanym numerem strony
                var pageNum = typeof f.page !== 'undefined' ? f.page : 0;
                html += '<td><button type="button" class="btn btn-secondary btn-sm preview-btn" data-page="' + pageNum + '">Pokaż</button></td>';
            }
            html += '</tr>';
        });
        html += '</tbody></table>';

        // Dodatkowy guzik "Podgląd całego dokumentu" jeśli to PDF
        html += '<div class="actions">';
        html += '<button id="confirm-btn" class="btn btn-primary">Zatwierdź i anonimizuj</button>';
        if (isPdf) {
            html += '<button id="full-preview-btn" class="btn btn-secondary">Podgląd całego dokumentu</button>';
        }
        html += '</div>';
        findingsDiv.innerHTML = html;

        // Event listener dla Zatwierdź
        var confirmBtn = document.getElementById('confirm-btn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function () {
                var checkedIds = [];
                var checkboxes = findingsDiv.querySelectorAll('input[type="checkbox"]:checked');
                checkboxes.forEach(function (cb) { checkedIds.push(cb.value); });

                statusDiv.textContent = 'Anonimizowanie...';

                var formData = new FormData();
                formData.append('file', selectedFile);
                formData.append('confirmed_ids', JSON.stringify(checkedIds));

                fetch('/anonymize', {
                    method: 'POST',
                    body: formData
                })
                .then(function (resp) {
                    if (!resp.ok) throw new Error('Blad serwera');
                    return resp.blob();
                })
                .then(function (blob) {
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = selectedFile.name.replace(/(\.[^.]+)$/, '_anonimizowany$1');
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                    statusDiv.textContent = 'Anonimizacja zakończona. Plik został pobrany.';
                })
                .catch(function (err) {
                    statusDiv.textContent = 'Błąd podczas anonimizacji.';
                    console.error(err);
                });
            });
        }

        // Event listenery dla przycisków Pokaż
        var previewBtns = findingsDiv.querySelectorAll('.preview-btn');
        previewBtns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var page = btn.getAttribute('data-page');
                // Znajdujemy wiersz tabeli i ID finding
                var row = btn.closest('tr');
                var checkbox = row.querySelector('input[type="checkbox"]');
                var highlightId = checkbox ? checkbox.value : '';
                loadPreview(parseInt(page, 10), highlightId);
            });
        });

        // Event listener dla Podglądu Całego Dokumentu
        var fullPreviewBtn = document.getElementById('full-preview-btn');
        if (fullPreviewBtn) {
            fullPreviewBtn.addEventListener('click', function () {
                loadPreview(0, ''); // Brak podświetlenia konkretnego elementu
            });
        }
    }

    function loadPreview(pageNum, highlightId) {
        if (!selectedFile) return;

        statusDiv.textContent = 'Generowanie podglądu strony...';

        // Zbieramy listę aktywnych checkboxów (te, które są zaznaczone)
        var activeIds = [];
        var checkboxes = findingsDiv.querySelectorAll('input[type="checkbox"]:checked');
        checkboxes.forEach(function (cb) { activeIds.push(cb.value); });

        var formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('page', pageNum);
        formData.append('active_ids', JSON.stringify(activeIds));
        formData.append('highlight_id', highlightId || '');

        fetch('/preview_page', {
            method: 'POST',
            body: formData
        })
        .then(function (resp) {
            if (!resp.ok) throw new Error('Błąd renderowania strony');
            return resp.blob();
        })
        .then(function (blob) {
            statusDiv.textContent = '';
            var url = URL.createObjectURL(blob);
            previewImage.src = url;
            previewPageNumSpan.textContent = pageNum + 1; // przyjaźniejsza indeksacja dla usera (1-based)

            // Dynamiczne sterowanie stronami (następna/poprzednia jeśli podgląd dokumentu)
            setupPreviewControls(pageNum, highlightId);

            modal.style.display = 'flex';
        })
        .catch(function (err) {
            statusDiv.textContent = 'Błąd pobierania podglądu.';
            console.error(err);
        });
    }

    function setupPreviewControls(currentPageNum, highlightId) {
        // Usuń stare sterowanie
        var oldControls = modal.querySelector('.modal-nav');
        if (oldControls) {
            oldControls.remove();
        }

        // Dodaj nawigację do modala
        var navDiv = document.createElement('div');
        navDiv.className = 'modal-nav';
        navDiv.style.marginTop = '15px';
        navDiv.style.display = 'flex';
        navDiv.style.justifyContent = 'center';
        navDiv.style.gap = '10px';

        var prevBtn = document.createElement('button');
        prevBtn.className = 'btn btn-secondary btn-sm';
        prevBtn.textContent = 'Poprzednia strona';
        prevBtn.disabled = currentPageNum <= 0;
        prevBtn.addEventListener('click', function () {
            loadPreview(currentPageNum - 1, highlightId);
        });

        var nextBtn = document.createElement('button');
        nextBtn.className = 'btn btn-secondary btn-sm';
        nextBtn.textContent = 'Następna strona';
        nextBtn.addEventListener('click', function () {
            loadPreview(currentPageNum + 1, highlightId);
        });

        navDiv.appendChild(prevBtn);
        navDiv.appendChild(nextBtn);
        modal.querySelector('.modal-content').appendChild(navDiv);
    }

    // Modal closing
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', function () {
            modal.style.display = 'none';
            if (previewImage.src) {
                URL.revokeObjectURL(previewImage.src);
                previewImage.src = '';
            }
        });
    }

    // Kliknięcie poza modal też zamyka
    window.addEventListener('click', function (e) {
        if (e.target === modal) {
            modal.style.display = 'none';
            if (previewImage.src) {
                URL.revokeObjectURL(previewImage.src);
                previewImage.src = '';
            }
        }
    });

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }
})();