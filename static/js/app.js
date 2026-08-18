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

        var isPdf = selectedFile && selectedFile.name.toLowerCase().endsWith ?
            selectedFile.name.toLowerCase().endsWith('.pdf') :
            /\.pdf$/i.test(selectedFile.name);

        var html = '<h2>Wykryte dane</h2>';
        html += '<table class="findings-table"><thead><tr><th>Typ</th><th>Znacznik</th><th>Pokrycie</th><th>Wystąpienia</th><th>Anonimizuj</th>';
        // html += '<table class="findings-table"><thead><tr><th>Typ</th><th>Znacznik</th><th>Siła</th><th>Powód</th><th>Liczba</th><th>Anonimizuj</th>';
        if (isPdf) {
            html += '<th>Akcje</th>';
        }
        html += '</tr></thead><tbody>';

        findings.forEach(function (f) {
            html += '<tr>';
            html += '<td>' + escapeHtml(f.entity_type) + '</td>';
            html += '<td>' + escapeHtml(f.marker) + '</td>';
            html += '<td>' + (f.score.toFixed(2) * 100) + '%</td>';
            // html += '<td>' + escapeHtml(f.reason) + '</td>';
            html += '<td>' + f.count + '</td>';
            html += '<td><div class="checkbox-wrapper-6"><input class="tgl tgl-light" id="cb1-6-' + f.id + '" type="checkbox" name="anonymize" value="' + f.id + '" checked><label class="tgl-btn" for="cb1-6-' + f.id + '"></label></div></td>';
            if (isPdf) {
                // Jeśli PDF, dajemy przycisk Pokaż z podanym numerem strony
                var pageNum = typeof f.page !== 'undefined' ? f.page : 0;
                html += '<td><button type="button" class="btn btn-secondary btn-sm preview-btn" data-page="' + pageNum + '"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 144C254.8 144 201.2 173.6 160.1 211.7C121.6 247.5 95 290 81.4 320C95 350 121.6 392.5 160.1 428.3C201.2 466.4 254.8 496 320 496C385.2 496 438.8 466.4 479.9 428.3C518.4 392.5 545 350 558.6 320C545 290 518.4 247.5 479.9 211.7C438.8 173.6 385.2 144 320 144zM127.4 176.6C174.5 132.8 239.2 96 320 96C400.8 96 465.5 132.8 512.6 176.6C559.4 220.1 590.7 272 605.6 307.7C608.9 315.6 608.9 324.4 605.6 332.3C590.7 368 559.4 420 512.6 463.4C465.5 507.1 400.8 544 320 544C239.2 544 174.5 507.2 127.4 463.4C80.6 419.9 49.3 368 34.4 332.3C31.1 324.4 31.1 315.6 34.4 307.7C49.3 272 80.6 220 127.4 176.6zM320 400C364.2 400 400 364.2 400 320C400 290.4 383.9 264.5 360 250.7C358.6 310.4 310.4 358.6 250.7 360C264.5 383.9 290.4 400 320 400zM240.4 311.6C242.9 311.9 245.4 312 248 312C283.3 312 312 283.3 312 248C312 245.4 311.8 242.9 311.6 240.4C274.2 244.3 244.4 274.1 240.5 311.5zM286 196.6C296.8 193.6 308.2 192.1 319.9 192.1C328.7 192.1 337.4 193 345.7 194.7C346 194.8 346.2 194.8 346.5 194.9C404.4 207.1 447.9 258.6 447.9 320.1C447.9 390.8 390.6 448.1 319.9 448.1C258.3 448.1 206.9 404.6 194.7 346.7C192.9 338.1 191.9 329.2 191.9 320.1C191.9 309.1 193.3 298.3 195.9 288.1C196.1 287.4 196.2 286.8 196.4 286.2C208.3 242.8 242.5 208.6 285.9 196.7z"/></svg> Pokaż</button></td>';
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

                var checkboxes = findingsDiv.querySelectorAll(
                    'input[type="checkbox"]:checked'
                );

                checkboxes.forEach(function (cb) {
                    checkedIds.push(cb.value);
                });

                statusDiv.textContent = 'Anonimizowanie...';

                var formData = new FormData();

                formData.append(
                    'file',
                    selectedFile
                );

                formData.append(
                    'confirmed_ids',
                    JSON.stringify(checkedIds)
                );

                var downloadFilename = null;

                fetch('/anonymize', {
                    method: 'POST',
                    body: formData
                })
                .then(function (resp) {
                    if (!resp.ok) {
                        throw new Error('Blad serwera');
                    }

                    // ------------------------------------------------
                    // Pobieramy nazwe pliku ustawiona przez backend:
                    //
                    // Content-Disposition:
                    // attachment; filename=anonimizacja_17-08_13-19.pdf
                    // ------------------------------------------------

                    var contentDisposition =
                        resp.headers.get(
                            'Content-Disposition'
                        );

                    if (contentDisposition) {

                        // Najpierw probujemy filename*=UTF-8''...
                        var utf8Match =
                            contentDisposition.match(
                                /filename\*=UTF-8''([^;]+)/i
                            );

                        if (
                            utf8Match
                            && utf8Match[1]
                        ) {
                            try {
                                downloadFilename =
                                    decodeURIComponent(
                                        utf8Match[1]
                                    );
                            } catch (e) {
                                downloadFilename =
                                    utf8Match[1];
                            }
                        }

                        // Jezeli nie bylo filename*=,
                        // probujemy zwykle filename=...
                        if (!downloadFilename) {
                            var filenameMatch =
                                contentDisposition.match(
                                    /filename="?([^";]+)"?/i
                                );

                            if (
                                filenameMatch
                                && filenameMatch[1]
                            ) {
                                downloadFilename =
                                    filenameMatch[1].trim();
                            }
                        }
                    }

                    return resp.blob();
                })
                .then(function (blob) {
                    var url =
                        URL.createObjectURL(blob);

                    var a =
                        document.createElement('a');

                    a.href = url;

                    // ------------------------------------------------
                    // Normalnie nazwa zawsze przyjdzie z backendu.
                    // ------------------------------------------------

                    if (downloadFilename) {
                        a.download =
                            downloadFilename;
                    } else {
                        // --------------------------------------------
                        // Fallback na wypadek braku naglowka.
                        //
                        // Nigdy nie uzywamy oryginalnej nazwy pliku.
                        // Zachowujemy tylko rozszerzenie.
                        // --------------------------------------------

                        var extension = '';

                        var extensionMatch =
                            selectedFile.name.match(
                                /(\.[^.]+)$/
                            );

                        if (
                            extensionMatch
                            && extensionMatch[1]
                        ) {
                            extension =
                                extensionMatch[1]
                                    .toLowerCase();
                        }

                        var now = new Date();

                        var day =
                            String(
                                now.getDate()
                            ).padStart(
                                2,
                                '0'
                            );

                        var month =
                            String(
                                now.getMonth() + 1
                            ).padStart(
                                2,
                                '0'
                            );

                        var hour =
                            String(
                                now.getHours()
                            ).padStart(
                                2,
                                '0'
                            );

                        var minute =
                            String(
                                now.getMinutes()
                            ).padStart(
                                2,
                                '0'
                            );

                        a.download =
                            'anonimizacja_'
                            + day
                            + '-'
                            + month
                            + '_'
                            + hour
                            + '-'
                            + minute
                            + extension;
                    }

                    document.body.appendChild(a);

                    a.click();

                    a.remove();

                    URL.revokeObjectURL(url);

                    statusDiv.textContent =
                        'Anonimizacja zakończona. '
                        + 'Plik został pobrany.';
                })
                .catch(function (err) {
                    statusDiv.textContent =
                        'Błąd podczas anonimizacji.';

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