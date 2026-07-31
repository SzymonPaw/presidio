/* app.js - prosty frontend dla anonimizatora */
(function () {
    'use strict';

    var form = document.getElementById('upload-form');
    var fileInput = document.getElementById('file-input');
    var fileLabel = document.querySelector('.file-label');
    var fileInfo = document.getElementById('file-info');
    var analyzeBtn = document.getElementById('analyze-btn');
    var statusDiv = document.getElementById('status');
    var findingsDiv = document.getElementById('findings');

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

        var html = '<h2>Wykryte dane</h2>';
        html += '<table class="findings-table"><thead><tr><th>Typ</th><th>Znacznik</th><th>Siła</th><th>Powód</th><th>Liczba</th><th>Anonimizuj</th></tr></thead><tbody>';
        findings.forEach(function (f) {
            html += '<tr>';
            html += '<td>' + escapeHtml(f.entity_type) + '</td>';
            html += '<td>' + escapeHtml(f.marker) + '</td>';
            html += '<td>' + f.score.toFixed(2) + '</td>';
            html += '<td>' + escapeHtml(f.reason) + '</td>';
            html += '<td>' + f.count + '</td>';
            html += '<td><input type="checkbox" name="anonymize" value="' + f.id + '" checked></td>';
            html += '</tr>';
        });
        html += '</tbody></table>';
        html += '<div class="actions"><button id="confirm-btn" class="btn btn-primary">Zatwierdź i anonimizuj</button></div>';
        findingsDiv.innerHTML = html;

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
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }
})();