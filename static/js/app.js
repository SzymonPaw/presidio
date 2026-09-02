import * as pdfjsLib from
    '/static/vendor/pdfjs/build/pdf.mjs';

import {
    EventBus,
    PDFLinkService,
    PDFFindController,
    PDFViewer
} from
    '/static/vendor/pdfjs/web/pdf_viewer.mjs';


pdfjsLib.GlobalWorkerOptions.workerSrc =
    '/static/vendor/pdfjs/build/pdf.worker.mjs';

/* app.js - frontend dla anonimizatora z podglądem PDF */
(function () {
    'use strict';

    var form = document.getElementById('upload-form');
    var fileInput = document.getElementById('file-input');
    var fileLabel = document.querySelector('.file-label');
    var fileInfo = document.getElementById('file-info');
    var documentList = document.getElementById('document-list');
    var analyzeBtn = document.getElementById('analyze-btn');
    var statusDiv = document.getElementById('status');
    var findingsDiv = document.getElementById('findings');

    var modal =
        document.getElementById(
            'preview-modal'
        );

    var modalCloseBtn =
        document.querySelector(
            '.close-btn'
        );

    var pdfViewerContainer =
        document.getElementById(
            'pdf-viewer-container'
        );

    var pdfViewerElement =
        document.getElementById(
            'pdf-viewer'
        );

    var pdfFindingsList =
        document.getElementById(
            'pdf-findings-list'
        );

    var pdfCurrentPage =
        document.getElementById(
            'pdf-current-page'
        );

    var pdfPageCount =
        document.getElementById(
            'pdf-page-count'
        );

    var pdfZoomInBtn =
        document.getElementById(
            'pdf-zoom-in'
        );

    var pdfZoomOutBtn =
        document.getElementById(
            'pdf-zoom-out'
        );

    var pdfZoomFitBtn =
        document.getElementById(
            'pdf-zoom-fit'
        );

    var pdfZoomValue =
        document.getElementById(
            'pdf-zoom-value'
        );

    var pdfSearchInput =
        document.getElementById(
            'pdf-search-input'
        );

    var pdfSearchPrev =
        document.getElementById(
            'pdf-search-prev'
        );

    var pdfSearchNext =
        document.getElementById(
            'pdf-search-next'
        );

    var previewModeDetectionsBtn =
        document.getElementById(
            'preview-mode-detections'
        );

    var previewModeOutputBtn =
        document.getElementById(
            'preview-mode-output'
        );


    var selectedFile = null;

    var currentFindings = [];

    var documents = [];
    var currentDocumentIndex = -1;


    var modalIsOpen = false;

    var pdfPreviewState = {
        loadingTask: null,
        pdfDocument: null,
        viewer: null,
        eventBus: null,
        linkService: null,
        findController: null,

        selectedFindingId: null,
        occurrenceIndex: {},

        loadedFile: null,
        ready: false,

        initialScaleApplied: false,
        previewMode: 'detections'
    };

    var xlsxSelectionState = {
        text: '',
        part: '',
        cellRef: '',
        cellElement: null
    };

    var docxSelectionState = {
        text: '',
        range: null
    };

    var xlsxZoomState = {
        scale: 1
    };

    var docxZoomState = {
        scale: 1
    };

    var xlsxSearchState = {
        hits: [],
        currentIndex: -1
    };

    var docxSearchState = {
        hits: [],
        currentIndex: -1
    };

    pdfPreviewState.selectedManualFindingId = null;

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
                handleFiles(files);
            }
        });
    }

    // Klikniecie w label
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            if (fileInput.files.length > 0) {
                handleFiles(fileInput.files);
            }
        });
    }

    function handleFiles(fileList) {
        var files = Array.prototype.slice.call(fileList);
        var availableSlots = 8 - documents.length;

        if (availableSlots <= 0) {
            statusDiv.textContent = 'Można dodać maksymalnie 8 plików.';
            fileInput.value = '';
            return;
        }

        if (files.length > availableSlots) {
            statusDiv.textContent =
                'Można dodać jeszcze tylko ' + availableSlots + ' plik'
                + (availableSlots === 1 ? '.' : 'i.');
            files = files.slice(0, availableSlots);
        } else {
            statusDiv.textContent = '';
        }

        files.forEach(function (file) {
            documents.push({
                file: file,
                findings: [],
                manualFindings: [],
                analyzed: false,
                status: 'Oczekuje na analizę'
            });
        });

        if (currentDocumentIndex < 0) {
            currentDocumentIndex = 0;
        }

        switchDocument(currentDocumentIndex);
        renderDocumentList();
        analyzeBtn.disabled = documents.length === 0;
        fileInput.value = '';
    }

    function switchDocument(index) {
        persistCurrentFindingsState();

        if (!documents[index]) {
            selectedFile = null;
            currentFindings = [];
            return;
        }

        currentDocumentIndex = index;
        selectedFile = documents[index].file;
        currentFindings = documents[index].findings;
        resetPdfPreview();

        findingsDiv.innerHTML = documents[index].analyzed ? '' :
            '<p>Dokument oczekuje na analizę.</p>';

        fileInfo.textContent =
            'Wybrany plik: '
            + selectedFile.name
            + ' ('
            + formatSize(selectedFile.size)
            + ')';

        if (documents[index].analyzed) {
            renderFindings(currentFindings);
        }

        renderDocumentList();
    }

    function persistCurrentFindingsState() {
        if (currentDocumentIndex < 0 || !documents[currentDocumentIndex].analyzed) {
            return;
        }

        var checkboxes = findingsDiv.querySelectorAll('input[name="anonymize"]');
        checkboxes.forEach(function (checkbox) {
            var finding = documents[currentDocumentIndex].findings.find(function (item) {
                return String(item.id) === String(checkbox.value);
            });
            if (finding) finding.enabled = checkbox.checked;
        });
    }

    function renderDocumentList() {
        if (!documentList) return;

        documentList.innerHTML = documents.map(function (item, index) {
            var activeClass = index === currentDocumentIndex ? ' is-active' : '';
            var downloadDisabled = item.analyzed ? '' : ' disabled';
            var previewDisabled = item.analyzed ? '' : ' disabled';
            return '<div class="document-item' + activeClass + '">'
                + '<button type="button" class="document-select" data-document-index="' + index + '">'
                + escapeHtml(item.file.name)
                + ' <span>(' + escapeHtml(getFileType(item.file.name)) + ')</span>'
                + '<small>' + escapeHtml(item.status) + '</small>'
                + '</button>'
                + '<button type="button" class="btn btn-danger btn-sm document-remove" data-document-index="' + index + '"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M232.7 69.9L224 96L128 96C110.3 96 96 110.3 96 128C96 145.7 110.3 160 128 160L512 160C529.7 160 544 145.7 544 128C544 110.3 529.7 96 512 96L416 96L407.3 69.9C402.9 56.8 390.7 48 376.9 48L263.1 48C249.3 48 237.1 56.8 232.7 69.9zM512 208L128 208L149.1 531.1C150.7 556.4 171.7 576 197 576L443 576C468.3 576 489.3 556.4 490.9 531.1L512 208z"/></svg> Usuń</button>'
                + '<button type="button" class="btn btn-secondary btn-sm document-preview" data-document-index="' + index + '"' + previewDisabled + '><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 144C254.8 144 201.2 173.6 160.1 211.7C121.6 247.5 95 290 81.4 320C95 350 121.6 392.5 160.1 428.3C201.2 466.4 254.8 496 320 496C385.2 496 438.8 466.4 479.9 428.3C518.4 392.5 545 350 558.6 320C545 290 518.4 247.5 479.9 211.7C438.8 173.6 385.2 144 320 144zM127.4 176.6C174.5 132.8 239.2 96 320 96C400.8 96 465.5 132.8 512.6 176.6C559.4 220.1 590.7 272 605.6 307.7C608.9 315.6 608.9 324.4 605.6 332.3C590.7 368 559.4 420 512.6 463.4C465.5 507.1 400.8 544 320 544C239.2 544 174.5 507.2 127.4 463.4C80.6 419.9 49.3 368 34.4 332.3C31.1 324.4 31.1 315.6 34.4 307.7C49.3 272 80.6 220 127.4 176.6zM320 400C364.2 400 400 364.2 400 320C400 290.4 383.9 264.5 360 250.7C358.6 310.4 310.4 358.6 250.7 360C264.5 383.9 290.4 400 320 400zM240.4 311.6C242.9 311.9 245.4 312 248 312C283.3 312 312 283.3 312 248C312 245.4 311.8 242.9 311.6 240.4C274.2 244.3 244.4 274.1 240.5 311.5zM286 196.6C296.8 193.6 308.2 192.1 319.9 192.1C328.7 192.1 337.4 193 345.7 194.7C346 194.8 346.2 194.8 346.5 194.9C404.4 207.1 447.9 258.6 447.9 320.1C447.9 390.8 390.6 448.1 319.9 448.1C258.3 448.1 206.9 404.6 194.7 346.7C192.9 338.1 191.9 329.2 191.9 320.1C191.9 309.1 193.3 298.3 195.9 288.1C196.1 287.4 196.2 286.8 196.4 286.2C208.3 242.8 242.5 208.6 285.9 196.7z"/></svg> Podgląd</button>'
                + '<button type="button" class="btn btn-primary btn-sm document-download" data-document-index="' + index + '"' + downloadDisabled + '><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M352 96C352 78.3 337.7 64 320 64C302.3 64 288 78.3 288 96L288 306.7L246.6 265.3C234.1 252.8 213.8 252.8 201.3 265.3C188.8 277.8 188.8 298.1 201.3 310.6L297.3 406.6C309.8 419.1 330.1 419.1 342.6 406.6L438.6 310.6C451.1 298.1 451.1 277.8 438.6 265.3C426.1 252.8 405.8 252.8 393.3 265.3L352 306.7L352 96zM160 384C124.7 384 96 412.7 96 448L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 448C544 412.7 515.3 384 480 384L433.1 384L376.5 440.6C345.3 471.8 294.6 471.8 263.4 440.6L206.9 384L160 384zM464 440C477.3 440 488 450.7 488 464C488 477.3 477.3 488 464 488C450.7 488 440 477.3 440 464C440 450.7 450.7 440 464 440z"></path></svg> Pobierz</button>'
                + '</div>';
        }).join('');

        documentList.querySelectorAll('.document-select').forEach(function (button) {
            button.addEventListener('click', function () {
                switchDocument(Number(button.getAttribute('data-document-index')));
            });
        });

        documentList.querySelectorAll('.document-remove').forEach(function (button) {
            button.addEventListener('click', function () {
                removeDocument(Number(button.getAttribute('data-document-index')));
            });
        });

        documentList.querySelectorAll('.document-download').forEach(function (button) {
            button.addEventListener('click', function () {
                switchDocument(Number(button.getAttribute('data-document-index')));
                var confirmButton = document.getElementById('confirm-btn');
                if (confirmButton) confirmButton.click();
            });
        });

        documentList.querySelectorAll('.document-preview').forEach(function (button) {
            button.addEventListener('click', function () {
                var index = Number(button.getAttribute('data-document-index'));
                if (!documents[index] || !documents[index].analyzed) {
                    return;
                }

                switchDocument(index);

                if (isSelectedFilePdf()) {
                    openPdfPreview(null);
                    return;
                }

                if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                    openDocxPreview(null);
                }
            });
        });
    }

    function removeDocument(index) {
        if (!documents[index]) {
            return;
        }

        persistCurrentFindingsState();

        if (index === currentDocumentIndex && modalIsOpen) {
            closePdfPreview();
        }

        documents.splice(index, 1);

        if (!documents.length) {
            currentDocumentIndex = -1;
            selectedFile = null;
            currentFindings = [];
            fileInfo.textContent = '';
            findingsDiv.innerHTML = '';
            statusDiv.textContent = '';
        } else if (index < currentDocumentIndex) {
            currentDocumentIndex -= 1;
        } else if (index === currentDocumentIndex) {
            currentDocumentIndex = Math.min(index, documents.length - 1);
            switchDocument(currentDocumentIndex);
        }

        analyzeBtn.disabled = documents.length === 0;
        renderDocumentList();
    }

    function getFileType(filename) {
        var extension = filename.split('.').pop().toUpperCase();
        return extension === filename.toUpperCase() ? 'plik' : extension;
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!documents.length) return;

            statusDiv.textContent = 'Analizowanie dokumentów...';
            analyzeBtn.disabled = true;

            documents.reduce(function (promise, document, index) {
                return promise.then(function () {
                    document.status = 'Analizowanie...';
                    renderDocumentList();
                    var formData = new FormData();
                    formData.append('file', document.file);
                    return fetch('/analyze', { method: 'POST', body: formData })
                        .then(function (resp) { return resp.json(); })
                        .then(function (data) {
                            if (data.error) throw new Error(data.error);
                            document.findings = data.findings || [];
                            document.analyzed = true;
                            document.status = 'Gotowy';
                        })
                        .catch(function (error) {
                            document.status = 'Błąd analizy';
                            console.error(error);
                        });
                });
            }, Promise.resolve()).then(function () {
                statusDiv.textContent = 'Analiza zakończona.';
                analyzeBtn.disabled = false;
                switchDocument(currentDocumentIndex);
                renderDocumentList();
            });
        });
    }

    function getCurrentManualFindings() {
        if (!documents[currentDocumentIndex]) {
            return [];
        }

        if (!Array.isArray(documents[currentDocumentIndex].manualFindings)) {
            documents[currentDocumentIndex].manualFindings = [];
        }

        return documents[currentDocumentIndex].manualFindings;
    }

    function getAllFindingEntries() {
        var items = (currentFindings || []).map(function (entry) {
            return Object.assign({}, entry);
        });

        var manualFindings = getCurrentManualFindings().filter(function (entry) {
            return entry.enabled !== false;
        });

        manualFindings.forEach(function (entry) {
            items.push(Object.assign({}, entry, {
                manual: true,
                entity_type: entry.entity_type || 'MANUAL',
                marker: entry.marker || '[DODANE_RĘCZNIE]',
                score: Number(entry.score) || 1,
                count: 1,
                raw_value: entry.raw_value || ''
            }));
        });

        return items;
    }

    function addManualFindingForCell(partName, cellRef, rawValue) {
        if (!isSelectedFileXlsx() || !documents[currentDocumentIndex]) {
            return null;
        }

        var value = (rawValue || '').trim();
        if (!value) {
            return null;
        }

        var manualFindings = getCurrentManualFindings();
        var duplicate = manualFindings.find(function (item) {
            return item.xlsx_part === partName && item.xlsx_cell === cellRef && item.raw_value === value;
        });

        if (duplicate) {
            duplicate.enabled = true;
            renderPdfFindingsSidebar();
            renderFindings(currentFindings);
            refreshXlsxManualHighlights();
            return duplicate;
        }

        var newFinding = {
            id: 'manual-' + Date.now() + '-' + Math.random().toString(16).slice(2),
            entity_type: 'MANUAL',
            marker: '[DODANE_RĘCZNIE]',
            raw_value: value,
            score: 1.0,
            reason: 'Dodane ręcznie',
            xlsx_part: partName,
            xlsx_cell: cellRef,
            enabled: true,
            manual: true
        };

        manualFindings.push(newFinding);

        renderPdfFindingsSidebar();
        renderFindings(currentFindings);
        refreshXlsxManualHighlights();
        return newFinding;
    }

    function addManualFindingForDocx(rawValue) {
        if (!isSelectedFileDocx() || !documents[currentDocumentIndex]) {
            return null;
        }

        var value = (rawValue || '').trim();
        if (!value) {
            return null;
        }

        var manualFindings = getCurrentManualFindings();
        var duplicate = manualFindings.find(function (item) {
            return !item.xlsx_part && !item.docx && item.raw_value === value;
        });

        if (duplicate) {
            duplicate.enabled = true;
            renderPdfFindingsSidebar();
            renderFindings(currentFindings);
            return duplicate;
        }

        var newFinding = {
            id: 'manual-' + Date.now() + '-' + Math.random().toString(16).slice(2),
            entity_type: 'MANUAL',
            marker: '[DODANE_RĘCZNIE]',
            raw_value: value,
            score: 1.0,
            reason: 'Dodane ręcznie',
            docx: true,
            enabled: true,
            manual: true
        };

        manualFindings.push(newFinding);
        renderPdfFindingsSidebar();
        renderFindings(currentFindings);
        return newFinding;
    }

    function removeManualFindingById(manualId) {
        if (!manualId) {
            return;
        }

        var manualFindings = getCurrentManualFindings();
        var index = manualFindings.findIndex(function (entry) {
            return String(entry.id) === String(manualId);
        });

        if (index < 0) {
            return;
        }

        var removedManualFinding = manualFindings[index];
        manualFindings.splice(index, 1);

        if (pdfViewerElement && (isSelectedFileXlsx() || isSelectedFileDocx())) {
            pdfViewerElement.querySelectorAll('.xlsx-hit.xlsx-manual-hit').forEach(function (hit) {
                if (String(hit.dataset.manualFindingId || '') === String(manualId)) {
                    var cell = hit.closest('.xlsx-preview-cell');
                    var originalValue = cell ? (cell.getAttribute('data-xlsx-value') || cell.textContent || '') : (hit.textContent || '');
                    if (hit.parentNode) {
                        hit.parentNode.replaceChild(document.createTextNode(String(originalValue)), hit);
                    }
                }
            });
            pdfViewerElement.querySelectorAll('.docx-hit[data-manual-finding-id]').forEach(function (hit) {
                if (String(hit.dataset.manualFindingId || '') === String(manualId) && hit.parentNode) {
                    var originalText = removedManualFinding
                        ? (removedManualFinding.raw_value || removedManualFinding.rawValue || '')
                        : '';
                    hit.parentNode.replaceChild(document.createTextNode(String(originalText || hit.textContent || '')), hit);
                }
            });

            if (isSelectedFileDocx()) {
                delete pdfViewerElement.dataset.docxOriginalHtml;
                pdfViewerElement.dataset.docxOriginalHtml = pdfViewerElement.innerHTML;
            }
        }

        renderPdfFindingsSidebar();
        renderFindings(currentFindings);
        refreshDocxPreviewState();
        refreshXlsxManualHighlights();
    }

    function resolveXlsxSelectionStateFromRange(range) {
        if (!range || !range.commonAncestorContainer) {
            return null;
        }

        var container = range.commonAncestorContainer;
        var cell = container.nodeType === 1 ? container : container.parentElement;
        var targetCell = cell && cell.closest ? cell.closest('.xlsx-preview-cell') : null;

        if (!targetCell) {
            return null;
        }

        var selectedText = (window.getSelection ? window.getSelection().toString() : '').trim();
        if (!selectedText) {
            return null;
        }

        var partName = targetCell.getAttribute('data-xlsx-part');
        var cellRef = targetCell.getAttribute('data-xlsx-cell');
        if (!partName || !cellRef) {
            return null;
        }

        return {
            text: selectedText,
            part: partName,
            cellRef: cellRef,
            cellElement: targetCell
        };
    }

    function clearXlsxSelectionState() {
        xlsxSelectionState = {
            text: '',
            part: '',
            cellRef: '',
            cellElement: null
        };
        if (pdfViewerElement) {
            pdfViewerElement.querySelectorAll('.xlsx-hit.is-selected-manual, .xlsx-hit.xlsx-manual-hit').forEach(function (mark) {
                var parent = mark.parentNode;
                if (!parent) {
                    return;
                }
                var textNode = document.createTextNode(mark.textContent || '');
                parent.replaceChild(textNode, mark);
            });
        }
        if (window.getSelection) {
            window.getSelection().removeAllRanges();
        }
        renderPdfFindingsSidebar();
    }

    function unwrapXlsxHighlights(cell) {
        if (!cell) {
            return;
        }

        cell.querySelectorAll('.xlsx-hit.xlsx-manual-hit, .xlsx-hit.is-selected-manual').forEach(function (mark) {
            var parent = mark.parentNode;
            if (!parent) {
                return;
            }
            var textNode = document.createTextNode(mark.textContent || '');
            parent.replaceChild(textNode, mark);
        });
    }

    function wrapXlsxTextInMark(cell, value, className, manualId) {
        if (!cell || !value) {
            return null;
        }

        unwrapXlsxHighlights(cell);

        var needle = String(value).trim();
        if (!needle) {
            return null;
        }

        var cellText = (cell.textContent || '').replace(/\r\n/g, '\n');
        var matchIndex = cellText.toLowerCase().indexOf(needle.toLowerCase());
        if (matchIndex < 0) {
            return null;
        }

        var walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
        var textNodes = [];
        while (walker.nextNode()) {
            textNodes.push(walker.currentNode);
        }

        if (!textNodes.length) {
            return null;
        }

        var currentIndex = 0;
        var startNode = null;
        var startOffset = 0;
        var endNode = null;
        var endOffset = 0;

        for (var i = 0; i < textNodes.length; i += 1) {
            var node = textNodes[i];
            var nodeText = (node.textContent || '').replace(/\r\n/g, '\n');
            var nextIndex = currentIndex + nodeText.length;

            if (startNode === null && matchIndex >= currentIndex && matchIndex < nextIndex) {
                startNode = node;
                startOffset = matchIndex - currentIndex;
            }

            if (startNode !== null && matchIndex + needle.length <= nextIndex) {
                endNode = node;
                endOffset = matchIndex + needle.length - currentIndex;
                break;
            }

            currentIndex = nextIndex;
        }

        if (!startNode || !endNode) {
            return null;
        }

        var mark = null;
        var range = document.createRange();
        try {
            range.setStart(startNode, startOffset);
            range.setEnd(endNode, endOffset);
            mark = document.createElement('mark');
            mark.className = 'xlsx-hit ' + className;
            if (manualId) {
                mark.setAttribute('data-manual-finding-id', String(manualId));
            }
            range.surroundContents(mark);
        } catch (error) {
            var startText = startNode.textContent || '';
            var endText = endNode.textContent || '';

            if (startNode === endNode) {
                var wholeText = startText;
                var before = wholeText.slice(0, startOffset);
                var matchText = wholeText.slice(startOffset, endOffset);
                var after = wholeText.slice(endOffset);
                var parent = startNode.parentNode;
                if (before) {
                    parent.insertBefore(document.createTextNode(before), startNode);
                }
                mark = document.createElement('mark');
                mark.className = 'xlsx-hit ' + className;
                if (manualId) {
                    mark.setAttribute('data-manual-finding-id', String(manualId));
                }
                mark.textContent = matchText;
                parent.insertBefore(mark, startNode);
                if (after) {
                    parent.insertBefore(document.createTextNode(after), startNode);
                }
                parent.removeChild(startNode);
                return mark;
            }

            if (startNode.parentNode === endNode.parentNode) {
                var parentNode = startNode.parentNode;
                var prefix = startText.slice(0, startOffset);
                var selectedText = startText.slice(startOffset);
                if (prefix) {
                    parentNode.insertBefore(document.createTextNode(prefix), startNode);
                }
                mark = document.createElement('mark');
                mark.className = 'xlsx-hit ' + className;
                if (manualId) {
                    mark.setAttribute('data-manual-finding-id', String(manualId));
                }
                mark.textContent = selectedText;
                parentNode.insertBefore(mark, startNode);
                parentNode.removeChild(startNode);

                var endAfter = endText.slice(endOffset);
                if (endAfter) {
                    parentNode.insertBefore(document.createTextNode(endAfter), endNode);
                }
                parentNode.removeChild(endNode);
                return mark;
            }
        }

        if (mark && manualId) {
            mark.setAttribute('data-manual-finding-id', String(manualId));
        }

        return mark;
    }

    function renderManualFindingsSection() {
        if (!documents[currentDocumentIndex] || !Array.isArray(documents[currentDocumentIndex].manualFindings)) {
            return '';
        }

        var manualFindings = documents[currentDocumentIndex].manualFindings.filter(function (entry) {
            return entry && entry.enabled !== false;
        });

        if (!manualFindings.length) {
            return '';
        }

        var html = '<div class="manual-findings-section"><h3>Dodane ręcznie</h3><table class="findings-table manual-findings-table"><thead><tr><th>Wartość</th><th>Znacznik</th><th>Usuń</th><th>Pokaż</th></tr></thead><tbody>';

        manualFindings.forEach(function (manualFinding) {
            html += '<tr>';
            html += '<td>' + escapeHtml(manualFinding.raw_value || '') + '</td>';
            html += '<td>' + escapeHtml(manualFinding.marker || '[DODANE_RĘCZNIE]') + '</td>';
            html += '<td><button type="button" style="margin: 0 auto;" class="btn btn-danger btn-sm manual-remove-main" data-manual-id="' + escapeHtml(String(manualFinding.id)) + '"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M232.7 69.9L224 96L128 96C110.3 96 96 110.3 96 128C96 145.7 110.3 160 128 160L512 160C529.7 160 544 145.7 544 128C544 110.3 529.7 96 512 96L416 96L407.3 69.9C402.9 56.8 390.7 48 376.9 48L263.1 48C249.3 48 237.1 56.8 232.7 69.9zM512 208L128 208L149.1 531.1C150.7 556.4 171.7 576 197 576L443 576C468.3 576 489.3 556.4 490.9 531.1L512 208z"></path></svg> Usuń</button></td>';
            html += '<td><button type="button" class="btn btn-secondary btn-sm manual-show-main" data-manual-id="' + escapeHtml(String(manualFinding.id)) + '"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 144C254.8 144 201.2 173.6 160.1 211.7C121.6 247.5 95 290 81.4 320C95 350 121.6 392.5 160.1 428.3C201.2 466.4 254.8 496 320 496C385.2 496 438.8 466.4 479.9 428.3C518.4 392.5 545 350 558.6 320C545 290 518.4 247.5 479.9 211.7C438.8 173.6 385.2 144 320 144zM127.4 176.6C174.5 132.8 239.2 96 320 96C400.8 96 465.5 132.8 512.6 176.6C559.4 220.1 590.7 272 605.6 307.7C608.9 315.6 608.9 324.4 605.6 332.3C590.7 368 559.4 420 512.6 463.4C465.5 507.1 400.8 544 320 544C239.2 544 174.5 507.2 127.4 463.4C80.6 419.9 49.3 368 34.4 332.3C31.1 324.4 31.1 315.6 34.4 307.7C49.3 272 80.6 220 127.4 176.6zM320 400C364.2 400 400 364.2 400 320C400 290.4 383.9 264.5 360 250.7C358.6 310.4 310.4 358.6 250.7 360C264.5 383.9 290.4 400 320 400zM240.4 311.6C242.9 311.9 245.4 312 248 312C283.3 312 312 283.3 312 248C312 245.4 311.8 242.9 311.6 240.4C274.2 244.3 244.4 274.1 240.5 311.5zM286 196.6C296.8 193.6 308.2 192.1 319.9 192.1C328.7 192.1 337.4 193 345.7 194.7C346 194.8 346.2 194.8 346.5 194.9C404.4 207.1 447.9 258.6 447.9 320.1C447.9 390.8 390.6 448.1 319.9 448.1C258.3 448.1 206.9 404.6 194.7 346.7C192.9 338.1 191.9 329.2 191.9 320.1C191.9 309.1 193.3 298.3 195.9 288.1C196.1 287.4 196.2 286.8 196.4 286.2C208.3 242.8 242.5 208.6 285.9 196.7z"></path></svg> Pokaż</button></td>';
            html += '</tr>';
        });

        html += '</tbody></table></div>';
        return html;
    }

    function renderFindings(findings) {
        currentFindings =
            findings || [];

        var noFindingsMessage = currentFindings.length === 0 ?
            '<p>Brak wykrytych danych.</p>' : '';

        var isPdf = selectedFile && selectedFile.name.toLowerCase().endsWith ?
            selectedFile.name.toLowerCase().endsWith('.pdf') :
            /\.pdf$/i.test(selectedFile.name);

        var isDocx = selectedFile && selectedFile.name.toLowerCase().endsWith ?
            selectedFile.name.toLowerCase().endsWith('.docx') :
            /\.docx$/i.test(selectedFile.name);

        var isXlsx = selectedFile && selectedFile.name.toLowerCase().endsWith ?
            selectedFile.name.toLowerCase().endsWith('.xlsx') :
            /\.xlsx$/i.test(selectedFile.name);

        var html = noFindingsMessage + '<h2>Wykryte dane</h2>';
        html += '<table class="findings-table"><thead><tr><th>Typ</th><th>Znacznik</th><th>Pokrycie</th><th>Wystąpienia</th><th>Anonimizuj</th>';
        if (isPdf || isDocx || isXlsx) {
            html += '<th>Akcje</th>';
        }
        html += '</tr></thead><tbody>';

        currentFindings.forEach(function (f) {
            html += '<tr>';
            html += '<td>' + escapeHtml(f.entity_type) + '</td>';
            html += '<td>' + escapeHtml(f.marker) + '</td>';
            html += '<td>' + (f.score.toFixed(2) * 100) + '%</td>';
            // html += '<td>' + escapeHtml(f.reason) + '</td>';
            html += '<td>' + f.count + '</td>';
            var checkedAttribute = f.enabled !== false ? ' checked' : '';
            html += '<td><div class="checkbox-wrapper-6"><input class="tgl tgl-light" id="cb1-6-' + f.id + '" type="checkbox" name="anonymize" value="' + f.id + '"' + checkedAttribute + '><label class="tgl-btn" for="cb1-6-' + f.id + '"></label></div></td>';
            if (isPdf || isDocx || isXlsx) {
                // Wspólny przycisk podglądu dla PDF, DOCX i XLSX.
                html +=
                    '<td>'
                    + '<button '
                    + 'type="button" '
                    + 'class="btn btn-secondary btn-sm preview-btn" '
                    + 'data-finding-id="' + f.id + '">'
                    + '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 144C254.8 144 201.2 173.6 160.1 211.7C121.6 247.5 95 290 81.4 320C95 350 121.6 392.5 160.1 428.3C201.2 466.4 254.8 496 320 496C385.2 496 438.8 466.4 479.9 428.3C518.4 392.5 545 350 558.6 320C545 290 518.4 247.5 479.9 211.7C438.8 173.6 385.2 144 320 144zM127.4 176.6C174.5 132.8 239.2 96 320 96C400.8 96 465.5 132.8 512.6 176.6C559.4 220.1 590.7 272 605.6 307.7C608.9 315.6 608.9 324.4 605.6 332.3C590.7 368 559.4 420 512.6 463.4C465.5 507.1 400.8 544 320 544C239.2 544 174.5 507.2 127.4 463.4C80.6 419.9 49.3 368 34.4 332.3C31.1 324.4 31.1 315.6 34.4 307.7C49.3 272 80.6 220 127.4 176.6zM320 400C364.2 400 400 364.2 400 320C400 290.4 383.9 264.5 360 250.7C358.6 310.4 310.4 358.6 250.7 360C264.5 383.9 290.4 400 320 400zM240.4 311.6C242.9 311.9 245.4 312 248 312C283.3 312 312 283.3 312 248C312 245.4 311.8 242.9 311.6 240.4C274.2 244.3 244.4 274.1 240.5 311.5zM286 196.6C296.8 193.6 308.2 192.1 319.9 192.1C328.7 192.1 337.4 193 345.7 194.7C346 194.8 346.2 194.8 346.5 194.9C404.4 207.1 447.9 258.6 447.9 320.1C447.9 390.8 390.6 448.1 319.9 448.1C258.3 448.1 206.9 404.6 194.7 346.7C192.9 338.1 191.9 329.2 191.9 320.1C191.9 309.1 193.3 298.3 195.9 288.1C196.1 287.4 196.2 286.8 196.4 286.2C208.3 242.8 242.5 208.6 285.9 196.7z"/></svg>'
                    + 'Pokaż'
                    + '</button>'
                    + '</td>';
            }
            html += '</tr>';
        });
        html += '</tbody></table>';
        html += renderManualFindingsSection();

        // Dodatkowy guzik "Podgląd całego dokumentu" jeśli to PDF
        html += '<div class="actions">';
        html += '<button id="confirm-btn" class="btn btn-primary"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M352 96C352 78.3 337.7 64 320 64C302.3 64 288 78.3 288 96L288 306.7L246.6 265.3C234.1 252.8 213.8 252.8 201.3 265.3C188.8 277.8 188.8 298.1 201.3 310.6L297.3 406.6C309.8 419.1 330.1 419.1 342.6 406.6L438.6 310.6C451.1 298.1 451.1 277.8 438.6 265.3C426.1 252.8 405.8 252.8 393.3 265.3L352 306.7L352 96zM160 384C124.7 384 96 412.7 96 448L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 448C544 412.7 515.3 384 480 384L433.1 384L376.5 440.6C345.3 471.8 294.6 471.8 263.4 440.6L206.9 384L160 384zM464 440C477.3 440 488 450.7 488 464C488 477.3 477.3 488 464 488C450.7 488 440 477.3 440 464C440 450.7 450.7 440 464 440z"/></svg> Zatwierdź i pobierz</button>';
        if (isPdf || isDocx || isXlsx) {
            html += '<button id="full-preview-btn" class="btn btn-secondary"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 144C254.8 144 201.2 173.6 160.1 211.7C121.6 247.5 95 290 81.4 320C95 350 121.6 392.5 160.1 428.3C201.2 466.4 254.8 496 320 496C385.2 496 438.8 466.4 479.9 428.3C518.4 392.5 545 350 558.6 320C545 290 518.4 247.5 479.9 211.7C438.8 173.6 385.2 144 320 144zM127.4 176.6C174.5 132.8 239.2 96 320 96C400.8 96 465.5 132.8 512.6 176.6C559.4 220.1 590.7 272 605.6 307.7C608.9 315.6 608.9 324.4 605.6 332.3C590.7 368 559.4 420 512.6 463.4C465.5 507.1 400.8 544 320 544C239.2 544 174.5 507.2 127.4 463.4C80.6 419.9 49.3 368 34.4 332.3C31.1 324.4 31.1 315.6 34.4 307.7C49.3 272 80.6 220 127.4 176.6zM320 400C364.2 400 400 364.2 400 320C400 290.4 383.9 264.5 360 250.7C358.6 310.4 310.4 358.6 250.7 360C264.5 383.9 290.4 400 320 400zM240.4 311.6C242.9 311.9 245.4 312 248 312C283.3 312 312 283.3 312 248C312 245.4 311.8 242.9 311.6 240.4C274.2 244.3 244.4 274.1 240.5 311.5zM286 196.6C296.8 193.6 308.2 192.1 319.9 192.1C328.7 192.1 337.4 193 345.7 194.7C346 194.8 346.2 194.8 346.5 194.9C404.4 207.1 447.9 258.6 447.9 320.1C447.9 390.8 390.6 448.1 319.9 448.1C258.3 448.1 206.9 404.6 194.7 346.7C192.9 338.1 191.9 329.2 191.9 320.1C191.9 309.1 193.3 298.3 195.9 288.1C196.1 287.4 196.2 286.8 196.4 286.2C208.3 242.8 242.5 208.6 285.9 196.7z"/></svg> Podgląd dokumentu</button>';
        }
        html += '</div>';
        findingsDiv.innerHTML = html;

        // ---------------------------------------------------------
        // PDF.js - otwieranie podgladu
        // ---------------------------------------------------------

        var previewBtns =
            findingsDiv.querySelectorAll(
                '.preview-btn'
            );

        previewBtns.forEach(
            function (button) {
                button.addEventListener(
                    'click',
                    function () {
                        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                            openDocxPreview(
                                button.getAttribute(
                                    'data-finding-id'
                                )
                            );
                            return;
                        }

                        openPdfPreview(
                            button.getAttribute(
                                'data-finding-id'
                            )
                        );
                    }
                );
            }
        );


        var fullPreviewBtn =
            document.getElementById(
                'full-preview-btn'
            );

        if (fullPreviewBtn) {
            fullPreviewBtn.addEventListener(
                'click',
                function () {
                    if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                        openDocxPreview(
                            null
                        );
                        return;
                    }

                    openPdfPreview(
                        null
                    );
                }
            );
        }

        var mainCheckboxes =
            findingsDiv.querySelectorAll(
                'input[name="anonymize"]'
            );

        mainCheckboxes.forEach(
            function (checkbox) {
                checkbox.addEventListener(
                    'change',
                    function () {
                        var finding = getFindingById(checkbox.value);
                        if (finding) finding.enabled = checkbox.checked;
                        renderPdfFindingsSidebar();
                        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                            refreshDocxPreviewState();
                        } else {
                            refreshPdfOverlayState();
                        }
                    }
                );
            }
        );

        // Event listener dla Zatwierdź
        var manualMainShowButtons = findingsDiv.querySelectorAll('.manual-show-main');
        manualMainShowButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var manualId = button.getAttribute('data-manual-id');
                var manualFinding = getCurrentManualFindings().find(function (entry) {
                    return String(entry.id) === String(manualId);
                });

                if (!manualFinding) {
                    return;
                }

                openDocxPreview(null, manualFinding.id);
            });
        });

        var manualMainRemoveButtons = findingsDiv.querySelectorAll('.manual-remove-main');
        manualMainRemoveButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                removeManualFindingById(button.getAttribute('data-manual-id'));
            });
        });

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

                if (documents[currentDocumentIndex]) {
                    documents[currentDocumentIndex].status = 'Anonimizowanie...';
                    renderDocumentList();
                }
                statusDiv.textContent = 'Anonimizowanie...';

                var formData = new FormData();
                var manualFindings = getCurrentManualFindings().filter(function (item) {
                    return item.enabled !== false;
                }).map(function (item) {
                    return {
                        entity_type: item.entity_type || 'MANUAL',
                        marker: item.marker || '[DODANE_RĘCZNIE]',
                        raw_value: item.raw_value,
                        score: item.score || 1,
                        reason: item.reason || 'Dodane ręcznie',
                        xlsx_part: item.xlsx_part,
                        xlsx_cell: item.xlsx_cell,
                    };
                });

                formData.append(
                    'file',
                    selectedFile
                );

                formData.append(
                    'confirmed_ids',
                    JSON.stringify(checkedIds)
                );

                formData.append(
                    'manual_findings',
                    JSON.stringify(manualFindings)
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

                    if (documents[currentDocumentIndex]) {
                        documents[currentDocumentIndex].status = 'Pobrany';
                        renderDocumentList();
                    }
                })
                .catch(function (err) {
                    statusDiv.textContent =
                        'Błąd podczas anonimizacji.';

                    if (documents[currentDocumentIndex]) {
                        documents[currentDocumentIndex].status = 'Błąd anonimizacji';
                        renderDocumentList();
                    }

                    console.error(err);
                });
            });
        }
    }

    function isSelectedFilePdf() {
        return Boolean(
            selectedFile
            && /\.pdf$/i.test(
                selectedFile.name
            )
        );
    }

    function isSelectedFileDocx() {
        return Boolean(
            selectedFile
            && /\.docx$/i.test(
                selectedFile.name
            )
        );
    }

    function isSelectedFileXlsx() {
        return Boolean(
            selectedFile
            && /\.xlsx$/i.test(
                selectedFile.name
            )
        );
    }

    function getFindingById(
        findingId
    ) {
        var allFindings = getAllFindingEntries();
        return (
            allFindings.find(
                function (finding) {
                    return (
                        String(finding.id)
                        === String(findingId)
                    );
                }
            )
            || null
        );
    }


    function getFindingOccurrences(
        finding
    ) {
        if (!finding) {
            return [];
        }

        if (
            Array.isArray(
                finding.occurrences
            )
            && finding.occurrences.length
        ) {
            return finding.occurrences;
        }

        if (
            typeof finding.page
            !== 'undefined'
        ) {
            return [
                {
                    page:
                        finding.page,

                    bbox:
                        finding.bbox,

                    pdf_bbox:
                        finding.pdf_bbox
                }
            ];
        }

        return [];
    }


    function getMainFindingCheckbox(
        findingId
    ) {
        var checkboxes =
            findingsDiv.querySelectorAll(
                'input[name="anonymize"]'
            );

        for (
            var i = 0;
            i < checkboxes.length;
            i++
        ) {
            if (
                String(
                    checkboxes[i].value
                )
                === String(
                    findingId
                )
            ) {
                return checkboxes[i];
            }
        }

        return null;
    }


    function isFindingActive(
        findingId
    ) {
        var checkbox =
            getMainFindingCheckbox(
                findingId
            );

        return Boolean(
            checkbox
            && checkbox.checked
        );
    }


    function setFindingActive(
        findingId,
        checked
    ) {
        var checkbox =
            getMainFindingCheckbox(
                findingId
            );

        if (!checkbox) {
            return;
        }

        checkbox.checked =
            Boolean(
                checked
            );

        checkbox.dispatchEvent(
            new Event(
                'change',
                {
                    bubbles: true
                }
            )
        );
    }


    // =========================================================
    // Reset PDF
    // =========================================================

    function resetPdfPreview() {

        if (
            pdfPreviewState.loadingTask
        ) {
            try {
                pdfPreviewState
                    .loadingTask
                    .destroy();
            } catch (error) {
                console.debug(
                    error
                );
            }
        }

        if (
            pdfPreviewState.pdfDocument
        ) {
            try {
                pdfPreviewState
                    .pdfDocument
                    .destroy();
            } catch (error) {
                console.debug(
                    error
                );
            }
        }
        // Jeśli istnieje aktywny viewer/linkService/findController,
        // spróbuj odłączyć dokumenty i posprzątać, aby nie zostawić
        // wiszących referencji, które mogłyby zablokować kolejne
        // otwarcia podglądu.
        try {
            var _oldViewer = pdfPreviewState.viewer;

            if (
                _oldViewer
                && typeof _oldViewer.setDocument === 'function'
            ) {
                try {
                    _oldViewer.setDocument(null);
                } catch (e) {
                    // ignore
                }
            }

            if (
                pdfPreviewState.linkService
                && typeof pdfPreviewState.linkService.setDocument === 'function'
            ) {
                try {
                    pdfPreviewState.linkService.setDocument(null, null);
                } catch (e) {
                    // ignore
                }
            }

            if (
                pdfPreviewState.findController
                && typeof pdfPreviewState.findController.setDocument === 'function'
            ) {
                try {
                    pdfPreviewState.findController.setDocument(null);
                } catch (e) {
                    // ignore
                }
            }

            if (
                _oldViewer
                && typeof _oldViewer.cleanup === 'function'
            ) {
                try {
                    _oldViewer.cleanup();
                } catch (e) {
                    // ignore
                }
            }
        } catch (e) {
            console.debug('Error cleaning old viewer/linkService/findController', e);
        }


        pdfPreviewState = {
            loadingTask: null,
            pdfDocument: null,
            viewer: null,
            eventBus: null,
            linkService: null,
            findController: null,

            selectedFindingId: null,
            occurrenceIndex: {},

            loadedFile: null,
            ready: false,
            previewMode: 'detections',
            initialScaleApplied: false,
            activeXlsxSheetName: null
        };


        if (pdfViewerElement) {
            pdfViewerElement.innerHTML =
                '';
        }

        if (pdfViewerContainer) {

            pdfViewerContainer.scrollTop =
                0;

            pdfViewerContainer.scrollLeft =
                0;

            pdfViewerContainer
                .classList
                .remove(
                    'is-over-pii'
                );
        }

        if (pdfFindingsList) {
            pdfFindingsList.innerHTML =
                '';
        }

        if (pdfCurrentPage) {
            pdfCurrentPage.textContent =
                '1';
        }

        if (pdfPageCount) {
            pdfPageCount.textContent =
                '0';
        }


        pdfPreviewState.previewMode = 'detections';

        if (previewModeDetectionsBtn) {
            previewModeDetectionsBtn.classList.add('is-active');
        }

        if (previewModeOutputBtn) {
            previewModeOutputBtn.classList.remove('is-active');
        }
    }

    function waitForPdfLayoutReady(
        viewer
    ) {

        return new Promise(
            function (resolve) {

                var attempts = 0;

                var maxAttempts = 60;


                function checkLayout() {

                    attempts += 1;


                    if (!pdfViewerContainer) {
                        resolve(false);
                        return;
                    }


                    var containerRect =
                        pdfViewerContainer
                            .getBoundingClientRect();


                    var containerReady =
                        containerRect.width > 0
                        && containerRect.height > 0;


                    // Jeżeli viewer jeszcze nie istnieje,
                    // wystarczy nam gotowy kontener modala.

                    if (!viewer) {

                        if (containerReady) {

                            requestAnimationFrame(
                                function () {
                                    resolve(true);
                                }
                            );

                            return;
                        }

                    } else {

                        // Przy pagesinit wymagamy dodatkowo,
                        // żeby pierwsza strona PDF naprawdę
                        // uczestniczyła już w layoucie DOM.

                        var firstPage =
                            viewer.getPageView(
                                0
                            );


                        var pageDiv =
                            firstPage
                                ? firstPage.div
                                : null;


                        var pageReady =
                            Boolean(
                                pageDiv
                                && pageDiv.isConnected
                                && pageDiv.offsetParent
                                    !== null
                            );


                        if (
                            containerReady
                            && pageReady
                        ) {

                            requestAnimationFrame(
                                function () {
                                    resolve(true);
                                }
                            );

                            return;
                        }
                    }


                    if (
                        attempts >= maxAttempts
                    ) {

                        resolve(false);
                        return;
                    }


                    requestAnimationFrame(
                        checkLayout
                    );
                }


                requestAnimationFrame(
                    checkLayout
                );
            }
        );
    }

    // =========================================================
    // Ładowanie całego PDF
    // =========================================================

    async function ensurePdfPreviewLoaded() {

        if (
            pdfPreviewState.ready
            && pdfPreviewState.viewer
            && pdfPreviewState.loadedFile
                === selectedFile
        ) {

            // Viewer istnieje i faktycznie
            // wyrenderował już dokument.
            //
            // Po ponownym pokazaniu modala
            // wymuszamy przeliczenie widocznych
            // stron.

            pdfPreviewState
                .viewer
                .update();

            return;
        }


        if (
            !selectedFile
            || !isSelectedFilePdf()
        ) {
            throw new Error(
                'Brak wybranego PDF.'
            );
        }


        var fileForPreview =
            selectedFile;


        resetPdfPreview();


        var eventBus =
            new EventBus();


        var linkService =
            new PDFLinkService({
                eventBus: eventBus
            });


        var findController =
            new PDFFindController({
                eventBus: eventBus,
                linkService: linkService
            });


        var viewer =
            new PDFViewer({
                container:
                    pdfViewerContainer,

                eventBus:
                    eventBus,

                linkService:
                    linkService,

                findController:
                    findController
            });


        linkService.setViewer(
            viewer
        );


        pdfPreviewState.eventBus =
            eventBus;

        pdfPreviewState.linkService =
            linkService;

        pdfPreviewState.findController =
            findController;

        pdfPreviewState.viewer =
            viewer;


        // PDF gotowy - pokazujemy wszystkie strony.
        eventBus.on(
            'pagesinit',
            function () {

                if (
                    pdfPageCount
                    && pdfPreviewState.pdfDocument
                ) {

                    pdfPageCount.textContent =
                        String(
                            pdfPreviewState
                                .pdfDocument
                                .numPages
                        );
                }


                renderPdfFindingsSidebar();


                // PDF.js sam wykonuje update podczas
                // inicjalizacji.
                //
                // Przy bardzo szybkim otwarciu modala
                // ten pierwszy update może nastąpić
                // zanim przeglądarka ustabilizuje
                // pozycje stron.
                //
                // Czekamy dwie klatki layoutu i
                // ponownie uruchamiamy rendering
                // widocznych stron.

                requestAnimationFrame(
                    function () {

                        requestAnimationFrame(
                            function () {

                                if (
                                    pdfPreviewState
                                        .viewer
                                    === viewer
                                ) {

                                    viewer.update();
                                }
                            }
                        );
                    }
                );
            }
        );


        // Każda wyrenderowana strona dostaje
        // osobną warstwę Presidio.
        eventBus.on(
            'pagerendered',
            function (event) {

                renderPdfOverlayForPage(
                    event.pageNumber - 1
                );

                if (
                    !pdfPreviewState.ready
                ) {

                    pdfPreviewState.ready =
                        true;

                    pdfPreviewState.loadedFile =
                        fileForPreview;
                }


                // Poczatkowa skale ustawiamy dopiero
                // po faktycznym wyrenderowaniu strony.
                //
                // W tym momencie pageView uczestniczy
                // juz w layoucie DOM, wiec PDF.js moze
                // bezpiecznie wykonac scrollPageIntoView.

                if (
                    !pdfPreviewState
                        .initialScaleApplied
                ) {

                    pdfPreviewState
                        .initialScaleApplied =
                        true;


                    requestAnimationFrame(
                        function () {

                            try {

                                viewer.currentScaleValue =
                                    'page-width';

                                updatePdfZoomValue();

                            } catch (error) {

                                console.warn(
                                    'Nie udalo sie ustawic '
                                    + 'poczatkowej skali PDF.',
                                    error
                                );
                            }
                        }
                    );
                }
            }
        );

        eventBus.on(
            'textlayerrendered',
            function (event) {
                renderPdfOverlayForPage(event.pageNumber - 1);
            }
        );


        eventBus.on(
            'pagechanging',
            function (event) {

                if (pdfCurrentPage) {
                    pdfCurrentPage.textContent =
                        String(
                            event.pageNumber
                        );
                }
            }
        );


        eventBus.on(
            'scalechanging',
            function () {
                updatePdfZoomValue();
            }
        );


        // Plik NIE jest wysyłany do żadnego CDN/API.
        // PDF.js dostaje bezpośrednio lokalne bajty File.
        var pdfBytes =
            new Uint8Array(
                await fileForPreview
                    .arrayBuffer()
            );


        var loadingTask =
            pdfjsLib.getDocument({
                data:
                    pdfBytes,

                cMapUrl:
                    '/static/vendor/pdfjs/web/cmaps/',

                cMapPacked:
                    true,

                standardFontDataUrl:
                    '/static/vendor/pdfjs/web/standard_fonts/',

                wasmUrl:
                    '/static/vendor/pdfjs/web/wasm/'
            });


        pdfPreviewState.loadingTask =
            loadingTask;


        var pdfDocument =
            await loadingTask.promise;


        pdfPreviewState.pdfDocument =
            pdfDocument;


        viewer.setDocument(
            pdfDocument
        );


        linkService.setDocument(
            pdfDocument,
            null
        );

        // Poczekaj na gotowość pierwszej strony. Nasłuchujemy zarówno
        // `pagesinit` (gdy pageViews są utworzone), jak i `pagerendered`
        // dla strony 1. Po rozwiązaniu usuwamy listener'y. Fallback: 5s.
        await new Promise(function (resolve) {
            if (
                pdfPreviewState.initialScaleApplied
                || pdfPreviewState.ready
            ) {
                resolve(true);
                return;
            }

            var resolved = false;

            function cleanup() {
                try {
                    eventBus.off('pagerendered', onPagerendered);
                    eventBus.off('pagesinit', onPagesinit);
                } catch (e) {
                    // ignore if `off` not present
                }
                clearTimeout(timeoutId);
            }

            function tryResolveIfPageReady(pageNumber) {
                if (resolved) return;

                if (!pdfPreviewState.viewer) return;

                var firstPage = pdfPreviewState.viewer.getPageView(0);

                var pageDiv = firstPage ? firstPage.div : null;

                var pageReady = Boolean(pageDiv && pageDiv.isConnected && pageDiv.offsetParent !== null);

                if (pageReady) {
                    resolved = true;
                    cleanup();
                    resolve(true);
                }
            }

            function onPagesinit() {
                tryResolveIfPageReady(1);
            }

            function onPagerendered(event) {
                // Prefers first page render; accept other pages only if
                // the first page is connected to layout.
                tryResolveIfPageReady(event.pageNumber);
            }

            // Register listeners (EventBus supports `on`; `off` may exist)
            eventBus.on('pagerendered', onPagerendered);
            eventBus.on('pagesinit', onPagesinit);

            var timeoutId = setTimeout(function () {
                if (resolved) return;
                resolved = true;
                try {
                    cleanup();
                } catch (e) {
                    // ignore
                }
                console.warn('Timeout waiting for first page render');

                try {
                    var containerRect = pdfViewerContainer ? pdfViewerContainer.getBoundingClientRect() : null;

                    console.debug('PDF preview timeout diagnostics:', {
                        containerRect: containerRect,
                        pdfPreviewState: pdfPreviewState
                    });

                    var firstView = pdfPreviewState && pdfPreviewState.viewer ? pdfPreviewState.viewer.getPageView(0) : null;
                    var pageDiv = firstView ? firstView.div : null;

                    console.debug('firstPageDiv exists:', Boolean(pageDiv), 'isConnected:', pageDiv ? pageDiv.isConnected : null, 'offsetParent:', pageDiv ? pageDiv.offsetParent : null);
                } catch (e) {
                    console.debug('Failed to collect diagnostics for PDF timeout', e);
                }

                resolve(false);
            }, 5000);
        });
    }


    // =========================================================
    // Otwieranie / zamykanie
    // =========================================================

    async function openDocxPreview(
        findingId,
        manualFindingId
    ) {
        if (!isSelectedFileDocx() && !isSelectedFileXlsx()) {
            return;
        }

        modalIsOpen = true;

        document.body.classList.add(
            'pdf-preview-open'
        );

        modal.style.display =
            'flex';

        modal.setAttribute(
            'aria-hidden',
            'false'
        );

        var isXlsx = isSelectedFileXlsx();
        var title = isXlsx ? 'Ładowanie podglądu XLSX...' : 'Ładowanie podglądu DOCX...';

        statusDiv.textContent = title;

        try {
            if (pdfViewerElement) {
                if (isXlsx) {
                    var xlsxFormData = new FormData();
                    xlsxFormData.append('file', selectedFile);
                    xlsxFormData.append('preview_mode', pdfPreviewState.previewMode || 'detections');

                    var manualFindings = getCurrentManualFindings().filter(function (item) {
                        return item.enabled !== false;
                    }).map(function (item) {
                        return {
                            id: item.id,
                            entity_type: item.entity_type || 'MANUAL',
                            marker: item.marker || '[DODANE_RĘCZNIE]',
                            raw_value: item.raw_value,
                            score: item.score || 1,
                            reason: item.reason || 'Dodane ręcznie',
                            xlsx_part: item.xlsx_part,
                            xlsx_cell: item.xlsx_cell,
                            manual: true,
                        };
                    });
                    xlsxFormData.append('manual_findings', JSON.stringify(manualFindings));

                    var xlsxResponse = await fetch('/preview-xlsx', { method: 'POST', body: xlsxFormData });
                    var xlsxPayload = await xlsxResponse.json();
                    if (!xlsxResponse.ok || xlsxPayload.error) {
                        throw new Error(xlsxPayload.error || 'Błąd podglądu XLSX.');
                    }
                    pdfViewerElement.innerHTML = xlsxPayload.html || '<div class="docx-preview-empty">Brak treści do podglądu.</div>';
                    pdfViewerElement.classList.add('docx-preview-container');
                    bindXlsxSheetTabs();
                    applyActiveXlsxSheet(pdfPreviewState.activeXlsxSheetName || getActiveXlsxSheetName());
                    applyXlsxZoom();
                    bindXlsxSelectionHandlers();
                    refreshXlsxManualHighlights();
                } else {
                    var previewBytes = selectedFile;
                    if ((pdfPreviewState.previewMode || 'detections') === 'output') {
                        previewBytes = await getAnonymizedPreviewBlob();
                    }
                    pdfViewerElement.innerHTML = '';
                    pdfViewerElement.classList.add('docx-preview-container');
                    await window.docx.renderAsync(
                        previewBytes,
                        pdfViewerElement,
                        null,
                        {
                            className: 'docxjs',
                            inWrapper: true,
                            breakPages: true,
                            ignoreWidth: false,
                            ignoreHeight: false,
                            renderHeaders: true,
                            renderFooters: true,
                            renderFootnotes: true,
                            renderEndnotes: true
                        }
                    );
                    pdfViewerElement.dataset.docxOriginalHtml = pdfViewerElement.innerHTML;
                    applyDocxZoom();
                    updatePdfZoomValue();
                    decorateDocxFindings((pdfPreviewState.previewMode || 'detections') === 'output');
                    decorateDocxManualFindings();
                    pdfViewerElement.dataset.docxOriginalHtml = pdfViewerElement.innerHTML;
                    bindDocxSelectionHandlers();
                }
            }

            if (pdfCurrentPage) {
                pdfCurrentPage.textContent = '1';
            }

            if (pdfPageCount) {
                pdfPageCount.textContent = '1';
            }

            renderPdfFindingsSidebar();
            refreshDocxPreviewState();

            if (isXlsx && manualFindingId) {
                focusManualXlsxFinding(manualFindingId);
            } else if (!isXlsx && manualFindingId) {
                focusManualDocxFinding(manualFindingId);
            } else if (findingId) {
                focusDocxFinding(findingId);
            }

            statusDiv.textContent = '';
        } catch (error) {
            statusDiv.textContent = isXlsx ? 'Błąd podglądu XLSX.' : 'Błąd podglądu DOCX.';
            console.error(error);
        }
    }

    async function getAnonymizedPreviewBlob() {
        var checkedIds = [];
        findingsDiv.querySelectorAll('input[type="checkbox"]:checked').forEach(function (checkbox) {
            checkedIds.push(checkbox.value);
        });

        var formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('confirmed_ids', JSON.stringify(checkedIds));

        var response = await fetch('/anonymize', { method: 'POST', body: formData });
        if (!response.ok) {
            throw new Error('Nie udało się przygotować podglądu po anonimizacji.');
        }
        return await response.blob();
    }

    function decorateDocxFindings(outputMode) {
        if (!pdfViewerElement) return;

        currentFindings.forEach(function (finding) {
            var text = outputMode ? finding.marker : finding.raw_value;
            if (!text) return;
            wrapDocxTextMatches(pdfViewerElement, String(text), finding.id);
        });
    }

    function decorateDocxManualFindings() {
        getCurrentManualFindings().filter(function (finding) {
            return finding.enabled !== false && finding.raw_value;
        }).forEach(function (finding) {
            wrapDocxTextMatches(pdfViewerElement, String(finding.raw_value), null, finding.id);
        });
    }

    function wrapDocxTextMatches(root, text, findingId, manualFindingId) {
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        var nodes = [];
        var node;
        while ((node = walker.nextNode())) {
            if (node.parentElement && !node.parentElement.closest('.docx-hit, style, script')) {
                nodes.push(node);
            }
        }

        nodes.forEach(function (textNode) {
            var value = textNode.nodeValue;
            var offset = value.indexOf(text);
            while (offset >= 0) {
                var matched = textNode.splitText(offset);
                var remainder = matched.splitText(text.length);
                var hit = document.createElement('span');
                hit.className = manualFindingId ? 'docx-hit docx-manual-hit' : 'docx-hit';
                if (findingId) {
                    hit.dataset.docxFindingId = findingId;
                }
                if (manualFindingId) {
                    hit.dataset.manualFindingId = String(manualFindingId);
                }
                hit.textContent = matched.nodeValue;
                matched.parentNode.replaceChild(hit, matched);
                textNode = remainder;
                value = textNode.nodeValue;
                offset = value.indexOf(text);
            }
        });
    }

    async function openPdfPreview(
        findingId
    ) {

        if (!isSelectedFilePdf()) {
            return;
        }

        document.body.classList.add(
            'pdf-preview-open'
        );

        modal.style.display =
            'flex';

        modal.setAttribute(
            'aria-hidden',
            'false'
        );

        // Jeśli viewer już istnieje (ponowne otwarcie), czekamy aż
        // jego pierwsza strona będzie podłączona do layoutu.
        await waitForPdfLayoutReady(
            pdfPreviewState.viewer || null
        );


        statusDiv.textContent =
            'Ładowanie podglądu PDF...';


        try {

            await ensurePdfPreviewLoaded();


            renderPdfFindingsSidebar();


            if (findingId) {
                focusPdfFinding(
                    findingId
                );
            }


            statusDiv.textContent =
                '';

        } catch (error) {

            statusDiv.textContent =
                'Błąd podglądu PDF.';

            console.error(
                error
            );
        }
    }


    function closePdfPreview() {
        modalIsOpen = false;

        modal.style.display =
            'none';

        modal.setAttribute(
            'aria-hidden',
            'true'
        );

        document.body.classList.remove(
            'pdf-preview-open'
        );

        // Usuń/posprzątaj stan preview przy zamknięciu, aby uniknąć
        // kumulacji listenerów i zasobów przy wielokrotnym otwieraniu.
        try {
            resetPdfPreview();
        } catch (e) {
            console.debug('Error during resetPdfPreview on close', e);
        }
    }


    // =========================================================
    // Overlay Presidio
    // =========================================================

    function refreshDocxPreviewState() {
        if (!pdfViewerElement || (!isSelectedFileDocx() && !isSelectedFileXlsx())) {
            return;
        }

        var outputMode = (pdfPreviewState.previewMode || 'detections') === 'output';

        pdfViewerElement.querySelectorAll('.docx-hit, .xlsx-hit').forEach(function (hit) {
            var findingId = hit.dataset.docxFindingId || hit.dataset.xlsxFindingId;
            var manualFindingId = hit.dataset.manualFindingId || null;

            if (hit.classList.contains('is-search-match') && !findingId && !manualFindingId) {
                return;
            }

            var manualFinding = null;
            var finding = null;

            if (manualFindingId) {
                manualFinding = getCurrentManualFindings().find(function (entry) {
                    return String(entry.id) === String(manualFindingId);
                });
            }

            if (!manualFinding) {
                finding = findingId ? getFindingById(findingId) : null;
            }

            var active = manualFinding ? manualFinding.enabled !== false : Boolean(finding && isFindingActive(findingId));
            var selected = manualFinding
                ? String(pdfPreviewState.selectedManualFindingId) === String(manualFindingId)
                : String(pdfPreviewState.selectedFindingId) === String(findingId);
            selected = selected && (active || outputMode);

            // Output mode: if anonymize enabled (active) -> show marker (is-output).
            // If anonymize disabled (not active) -> show raw value as plain text (do not hide).
            if (outputMode) {
                if (manualFinding) {
                    hit.classList.add('xlsx-manual-hit');
                    hit.dataset.manualFindingId = String(manualFindingId);
                } else {
                    hit.classList.remove('xlsx-manual-hit');
                    delete hit.dataset.manualFindingId;
                }

                if (active) {
                    hit.classList.remove('is-muted');
                    hit.classList.remove('is-hidden');
                    hit.classList.add('is-output');
                    try {
                        var marker = (manualFinding && manualFinding.marker)
                            || (finding && finding.marker)
                            || null;
                        if (marker !== null && marker !== undefined) {
                            hit.textContent = String(marker);
                        }
                    } catch (e) {
                        // ignore
                    }
                    hit.classList.toggle('is-selected', selected);
                } else {
                    hit.classList.remove('is-output');
                    hit.classList.remove('is-search-match');
                    hit.classList.remove('is-selected');
                    hit.classList.remove('is-hidden');
                    hit.classList.add('is-muted');
                    try {
                        var rawv = manualFinding
                            ? (manualFinding.raw_value || manualFinding.rawValue || '')
                            : (finding && (finding.raw_value || finding.rawValue || finding.rawValue)) || null;
                        if (rawv === null || rawv === undefined || rawv === '') {
                            rawv = (manualFinding && manualFinding.marker) || (finding && finding.marker) || hit.textContent;
                        }
                        hit.textContent = String(rawv);
                    } catch (e) {
                        // ignore
                    }
                }
                return;
            }

            // Detections mode: non-active findings shown as muted plain text, active may be selected
            var mutedInDetections = !active;
            hit.classList.toggle('is-hidden', false);
            hit.classList.toggle('is-output', false);
            hit.classList.toggle('is-muted', mutedInDetections);
            hit.classList.toggle('is-selected', selected && !mutedInDetections);
        });
    }

    function getActiveXlsxSheetName() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return pdfPreviewState.activeXlsxSheetName || null;
        }

        var activeTab = pdfViewerElement.querySelector('.xlsx-sheet-tab.is-active');
        if (activeTab) {
            return activeTab.getAttribute('data-sheet-name') || null;
        }

        var activePanel = pdfViewerElement.querySelector('.xlsx-sheet-panel.is-active');
        if (activePanel) {
            return activePanel.getAttribute('data-sheet-name') || null;
        }

        return pdfPreviewState.activeXlsxSheetName || null;
    }

    function applyActiveXlsxSheet(sheetName) {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        var targetSheet = sheetName || null;
        pdfPreviewState.activeXlsxSheetName = targetSheet;

        if (!targetSheet) {
            var firstTab = pdfViewerElement.querySelector('.xlsx-sheet-tab');
            if (firstTab) {
                targetSheet = firstTab.getAttribute('data-sheet-name') || null;
            }
        }

        if (!targetSheet) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-sheet-tab').forEach(function (tab) {
            tab.classList.toggle('is-active', tab.getAttribute('data-sheet-name') === targetSheet);
        });

        pdfViewerElement.querySelectorAll('.xlsx-sheet-panel').forEach(function (panel) {
            panel.classList.toggle('is-active', panel.getAttribute('data-sheet-name') === targetSheet);
        });
    }

    function bindXlsxSheetTabs() {
        if (!pdfViewerElement) {
            return;
        }

        var tabs = pdfViewerElement.querySelectorAll('.xlsx-sheet-tab');
        if (!tabs.length) {
            return;
        }

        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var targetName = tab.getAttribute('data-sheet-name');
                pdfPreviewState.activeXlsxSheetName = targetName || null;

                pdfViewerElement.querySelectorAll('.xlsx-sheet-tab').forEach(function (item) {
                    item.classList.toggle('is-active', item === tab);
                });

                pdfViewerElement.querySelectorAll('.xlsx-sheet-panel').forEach(function (panel) {
                    var active = panel.getAttribute('data-sheet-name') === targetName;
                    panel.classList.toggle('is-active', active);
                });
            });
        });
    }

    function confirmManualXlsxSelection() {
        if (!xlsxSelectionState.text) {
            return;
        }

        var manualFinding = addManualFindingForCell(
            xlsxSelectionState.part,
            xlsxSelectionState.cellRef,
            xlsxSelectionState.text
        );

        if (xlsxSelectionState.cellElement) {
            wrapXlsxTextInMark(
                xlsxSelectionState.cellElement,
                xlsxSelectionState.text,
                'xlsx-manual-hit',
                manualFinding && manualFinding.id
            );
            refreshXlsxManualHighlights();
        }

        xlsxSelectionState = {
            text: '',
            part: '',
            cellRef: '',
            cellElement: null
        };

        if (pdfViewerElement) {
            pdfViewerElement.querySelectorAll('.xlsx-preview-cell.is-selected-manual').forEach(function (cell) {
                cell.classList.remove('is-selected-manual');
            });
        }

        if (window.getSelection) {
            window.getSelection().removeAllRanges();
        }

        renderPdfFindingsSidebar();
    }

    function confirmManualDocxSelection() {
        if (!docxSelectionState.text) {
            return;
        }

        var manualFinding = addManualFindingForDocx(docxSelectionState.text);
        if (manualFinding && docxSelectionState.range && pdfViewerElement) {
            var selectedContents = docxSelectionState.range.extractContents();
            var mark = document.createElement('span');
            mark.className = 'docx-hit docx-manual-hit';
            mark.dataset.manualFindingId = String(manualFinding.id);
            mark.appendChild(selectedContents);
            docxSelectionState.range.insertNode(mark);
        }

        docxSelectionState = { text: '', range: null };
        if (window.getSelection) {
            window.getSelection().removeAllRanges();
        }
        refreshDocxPreviewState();
        pdfViewerElement.dataset.docxOriginalHtml = pdfViewerElement.innerHTML;
        renderPdfFindingsSidebar();
    }

    function resolveDocxSelectionStateFromRange(range) {
        if (!range || !pdfViewerElement || !pdfViewerElement.contains(range.commonAncestorContainer)) {
            return null;
        }

        var selectedText = (window.getSelection ? window.getSelection().toString() : '').trim();
        if (!selectedText) {
            return null;
        }

        return {
            text: selectedText,
            range: range.cloneRange()
        };
    }

    function syncDocxSelectionFromCurrentRange() {
        var selection = window.getSelection ? window.getSelection() : null;
        if (!selection || selection.rangeCount === 0) {
            return false;
        }

        var resolved = resolveDocxSelectionStateFromRange(selection.getRangeAt(0));
        if (!resolved) {
            return false;
        }

        docxSelectionState = resolved;
        renderPdfFindingsSidebar();
        return true;
    }

    function bindDocxSelectionHandlers() {
        if (!pdfViewerElement || !isSelectedFileDocx()) {
            return;
        }

        if (pdfViewerElement.dataset.docxSelectionHandlersBound === 'true') {
            return;
        }

        pdfViewerElement.dataset.docxSelectionHandlersBound = 'true';

        pdfViewerElement.addEventListener('mouseup', function () {
            syncDocxSelectionFromCurrentRange();
        });

        pdfViewerElement.addEventListener('click', function (event) {
            var manualHit = event.target.closest('.docx-manual-hit[data-manual-finding-id]');
            if (!manualHit || !pdfViewerElement.contains(manualHit)) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();
            docxSelectionState = { text: '', range: null };
            if (window.getSelection) {
                window.getSelection().removeAllRanges();
            }
            pdfPreviewState.selectedFindingId = null;
            focusManualDocxFinding(manualHit.dataset.manualFindingId);
        });
    }

    function focusManualDocxFinding(manualId) {
        if (!manualId || !pdfViewerElement || !isSelectedFileDocx()) {
            return;
        }

        var hit = null;
        pdfViewerElement.querySelectorAll('.docx-hit[data-manual-finding-id]').forEach(function (item) {
            if (!hit && String(item.dataset.manualFindingId) === String(manualId)) {
                hit = item;
            }
        });
        if (!hit) {
            return;
        }

        pdfPreviewState.selectedManualFindingId = String(manualId);
        refreshDocxPreviewState();
        hit.scrollIntoView({ block: 'center', behavior: 'smooth' });
        renderPdfFindingsSidebar();
        requestAnimationFrame(scrollManualSidebarToSelection);
    }

    function bindManualXlsxHitEvents() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-hit.xlsx-manual-hit').forEach(function (hit) {
            if (hit.dataset.manualXlsxBound === 'true') {
                return;
            }

            hit.dataset.manualXlsxBound = 'true';
            hit.addEventListener('click', function (event) {
                event.stopPropagation();
                if (!hit.dataset.manualFindingId) {
                    return;
                }
                focusManualXlsxFinding(hit.dataset.manualFindingId);
            });
        });
    }

    function clearXlsxSelectionStateForMode(mode) {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        if (mode === 'manual') {
            pdfPreviewState.selectedFindingId = null;
            pdfViewerElement.querySelectorAll('.xlsx-hit[data-xlsx-finding-id]').forEach(function (hit) {
                hit.classList.remove('is-selected');
            });
            if (pdfFindingsList) {
                pdfFindingsList.querySelectorAll('.pdf-finding-item.is-selected').forEach(function (item) {
                    item.classList.remove('is-selected');
                });
            }
        }

        if (mode === 'auto') {
            pdfPreviewState.selectedManualFindingId = null;
            pdfViewerElement.querySelectorAll('.xlsx-hit.xlsx-manual-hit').forEach(function (hit) {
                hit.classList.remove('is-selected');
            });
            if (pdfFindingsList) {
                pdfFindingsList.querySelectorAll('.pdf-manual-item.is-selected').forEach(function (item) {
                    item.classList.remove('is-selected');
                });
            }
        }
    }

    function syncSelectedXlsxManualMarks() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        var selectedManualId = pdfPreviewState.selectedManualFindingId || null;
        pdfViewerElement.querySelectorAll('.xlsx-hit.xlsx-manual-hit').forEach(function (hit) {
            var isSelected = selectedManualId && String(hit.dataset.manualFindingId) === String(selectedManualId);
            hit.classList.toggle('is-selected', Boolean(isSelected));
        });
    }

    function refreshXlsxManualHighlights() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        var outputMode = (pdfPreviewState.previewMode || 'detections') === 'output';

        if (outputMode) {
            pdfViewerElement.querySelectorAll('.xlsx-hit.xlsx-manual-hit').forEach(function (hit) {
                var manualId = hit.dataset.manualFindingId || null;
                var manualFinding = manualId ? getCurrentManualFindings().find(function (entry) {
                    return String(entry.id) === String(manualId);
                }) : null;

                if (!manualFinding) {
                    if (hit.parentNode) {
                        var staleValue = hit.textContent || '';
                        var staleCell = hit.closest('.xlsx-preview-cell');
                        if (staleCell) {
                            staleValue = staleCell.getAttribute('data-xlsx-value') || staleCell.textContent || staleValue;
                        }
                        var textNode = document.createTextNode(String(staleValue));
                        hit.parentNode.replaceChild(textNode, hit);
                    }
                    return;
                }

                var active = Boolean(manualFinding && manualFinding.enabled !== false);
                hit.classList.toggle('is-output', active);
                hit.classList.toggle('is-muted', !active);
                hit.classList.toggle('is-selected', Boolean(active && String(pdfPreviewState.selectedManualFindingId || '') === String(manualId)));

                if (active) {
                    hit.classList.remove('is-hidden');
                    hit.textContent = String((manualFinding && manualFinding.marker) || '[DODANE_RĘCZNIE]');
                } else {
                    hit.classList.remove('is-output');
                    hit.classList.remove('is-selected');
                    hit.classList.remove('is-hidden');
                    hit.classList.add('is-muted');

                    var originalText = manualFinding
                        ? (manualFinding.raw_value || manualFinding.rawValue || '')
                        : '';

                    if (!originalText) {
                        var previewCell = hit.closest('.xlsx-preview-cell');
                        originalText = previewCell ? (previewCell.getAttribute('data-xlsx-value') || previewCell.textContent || '') : (hit.textContent || '');
                    }

                    hit.textContent = String(originalText || hit.textContent || '');
                }
            });

            bindManualXlsxHitEvents();
            syncSelectedXlsxManualMarks();
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-preview-cell').forEach(function (cell) {
            unwrapXlsxHighlights(cell);
        });

        getCurrentManualFindings().filter(function (entry) {
            return entry.enabled !== false;
        }).forEach(function (entry) {
            if (!entry.xlsx_part || !entry.xlsx_cell || !entry.raw_value) {
                return;
            }

            var targetCell = null;
            pdfViewerElement.querySelectorAll('.xlsx-preview-cell').forEach(function (cell) {
                if (!targetCell && cell.getAttribute('data-xlsx-part') === entry.xlsx_part && cell.getAttribute('data-xlsx-cell') === entry.xlsx_cell) {
                    targetCell = cell;
                }
            });

            if (targetCell) {
                wrapXlsxTextInMark(targetCell, entry.raw_value, 'xlsx-manual-hit', entry.id);
            }
        });

        syncSelectedXlsxManualMarks();
        bindManualXlsxHitEvents();
    }

    function syncXlsxSelectionFromCurrentRange() {
        var selection = window.getSelection ? window.getSelection() : null;
        if (!selection || selection.rangeCount === 0) {
            return false;
        }

        var selectedText = selection.toString().trim();
        if (!selectedText) {
            return false;
        }

        var resolved = resolveXlsxSelectionStateFromRange(selection.getRangeAt(0));
        if (!resolved) {
            return false;
        }

        xlsxSelectionState = resolved;
        pdfViewerElement.querySelectorAll('.xlsx-preview-cell.is-selected-manual').forEach(function (cell) {
            cell.classList.remove('is-selected-manual');
        });
        if (resolved.cellElement) {
            resolved.cellElement.classList.add('is-selected-manual');
        }
        pdfPreviewState.selectedManualFindingId = null;
        renderPdfFindingsSidebar();
        return true;
    }

    function bindXlsxSelectionHandlers() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-preview-cell').forEach(function (cell) {
            cell.addEventListener('mouseup', function () {
                syncXlsxSelectionFromCurrentRange();
            });

            cell.addEventListener('click', function () {
                syncXlsxSelectionFromCurrentRange();
            });
        });

        document.addEventListener('selectionchange', function () {
            if (!isSelectedFileXlsx() || !pdfViewerElement) {
                return;
            }

            syncXlsxSelectionFromCurrentRange();
        });

        refreshXlsxManualHighlights();
    }

    function renderPdfOverlayForPage(
        pageIndex
    ) {

        if (
            !pdfPreviewState.viewer
        ) {
            return;
        }


        var pageView =
            pdfPreviewState.viewer
                .getPageView(
                    pageIndex
                );


        if (
            !pageView
            || !pageView.div
            || !pageView.viewport
        ) {
            return;
        }


        var oldLayer =
            pageView.div.querySelector(
                '.pii-overlay-layer'
            );


        if (oldLayer) {
            oldLayer.remove();
        }


        var layer =
            document.createElement(
                'div'
            );

        layer.className =
            'pii-overlay-layer';


        currentFindings.forEach(
            function (finding) {

                var occurrences =
                    getFindingOccurrences(
                        finding
                    );


                occurrences.forEach(
                    function (
                        occurrence,
                        occurrenceIndex
                    ) {

                        if (
                            Number(
                                occurrence.page
                            )
                            !== pageIndex
                        ) {
                            return;
                        }


                        if (
                            !Array.isArray(
                                occurrence.pdf_bbox
                            )
                            || occurrence
                                .pdf_bbox
                                .length !== 4
                        ) {
                            return;
                        }


                        var pdfBox =
                            occurrence.pdf_bbox;

                        var textLayerRect = findPdfTextSpanRect(
                            pageView,
                            finding.raw_value,
                            pdfBox,
                            occurrences.slice(0, occurrenceIndex).filter(function (item) {
                                return Number(item.page) === pageIndex;
                            }).length
                        );

                        var left;
                        var top;
                        var width;
                        var height;

                        if (textLayerRect) {
                            var localRect = pdfScreenRectToPageRect(
                                pageView.div,
                                textLayerRect
                            );
                            left = localRect.left;
                            top = localRect.top;
                            width = localRect.width;
                            height = localRect.height;
                        } else {
                            var point1 =
                                pageView.viewport
                                .convertToViewportPoint(
                                    pdfBox[0],
                                    pdfBox[1]
                                );

                            var point2 =
                                pageView.viewport
                                .convertToViewportPoint(
                                    pdfBox[2],
                                    pdfBox[3]
                                );

                            left = Math.min(point1[0], point2[0]);
                            top = Math.min(point1[1], point2[1]);
                            width = Math.abs(point2[0] - point1[0]);
                            height = Math.abs(point2[1] - point1[1]);
                        }


                        var box =
                            document.createElement(
                                'div'
                            );


                        box.className =
                            'pii-overlay-box';


                        box.dataset.findingId =
                            String(
                                finding.id
                            );


                        box.dataset.occurrenceIndex =
                            String(
                                occurrenceIndex
                            );


                        box.style.left =
                            left + 'px';

                        box.style.top =
                            top + 'px';

                        box.style.width =
                            width + 'px';

                        box.style.height =
                            height + 'px';


                        layer.appendChild(
                            box
                        );
                    }
                );
            }
        );


        pageView.div.appendChild(
            layer
        );


        refreshPdfOverlayState();
    }

    function findPdfTextSpanRect(pageView, rawValue, pdfBox, occurrenceIndex) {
        if (!pageView || !pageView.div || !rawValue) {
            return null;
        }

        var searchText = String(rawValue);
        var spans = pageView.div.querySelectorAll('.textLayer span');
        var matches = Array.from(spans).filter(function (span) {
            return (span.textContent || '').indexOf(searchText) >= 0;
        });

        var span = matches[occurrenceIndex];
        if (matches.length > 1 && Array.isArray(pdfBox) && pdfBox.length === 4) {
            var point1 = pageView.viewport.convertToViewportPoint(pdfBox[0], pdfBox[1]);
            var point2 = pageView.viewport.convertToViewportPoint(pdfBox[2], pdfBox[3]);
            var expectedX = (Math.min(point1[0], point2[0]) + Math.max(point1[0], point2[0])) / 2;
            var expectedY = (Math.min(point1[1], point2[1]) + Math.max(point1[1], point2[1])) / 2;

            span = matches.reduce(function (closest, candidate) {
                var candidateRect = candidate.getBoundingClientRect();
                var pageRect = pageView.div.getBoundingClientRect();
                var candidateX = candidateRect.left - pageRect.left - pageView.div.clientLeft + candidateRect.width / 2;
                var candidateY = candidateRect.top - pageRect.top - pageView.div.clientTop + candidateRect.height / 2;
                var currentDistance = Math.hypot(candidateX - expectedX, candidateY - expectedY);
                if (!closest || currentDistance < closest.distance) {
                    return { element: candidate, distance: currentDistance };
                }
                return closest;
            }, null).element;
        }

        if (!span) {
            return null;
        }

        var spanText = span.textContent || '';
        var start = spanText.indexOf(searchText);
        if (start < 0 || !span.firstChild || span.firstChild.nodeType !== Node.TEXT_NODE) {
            return null;
        }

        var range = document.createRange();
        range.setStart(span.firstChild, start);
        range.setEnd(span.firstChild, start + searchText.length);

        var rects = Array.from(range.getClientRects());
        if (!rects.length) {
            return null;
        }

        // Keep a single local rectangle. Wrapped findings use the backend
        // geometry fallback instead of creating an oversized union.
        return rects.length === 1 ? rects[0] : null;
    }

    function pdfScreenRectToPageRect(pageElement, screenRect) {
        var pageRect = pageElement.getBoundingClientRect();
        var scaleX = pageRect.width / pageElement.clientWidth || 1;
        var scaleY = pageRect.height / pageElement.clientHeight || 1;

        return {
            left: (screenRect.left - pageRect.left - pageElement.clientLeft) / scaleX,
            top: (screenRect.top - pageRect.top - pageElement.clientTop) / scaleY,
            width: screenRect.width / scaleX,
            height: screenRect.height / scaleY
        };
    }


    function refreshPdfOverlayState() {

        if (!pdfViewerElement) {
            return;
        }


        var boxes =
            pdfViewerElement.querySelectorAll(
                '.pii-overlay-box'
            );


        boxes.forEach(
            function (box) {

                var findingId =
                    box.dataset.findingId;


                var finding =
                    getFindingById(
                        findingId
                    );


                if (!finding) {
                    return;
                }


                var active =
                    isFindingActive(
                        findingId
                    );


                box.classList.toggle(
                    'is-hidden',
                    !active
                );


                var selectedOccurrence =
                    pdfPreviewState
                        .occurrenceIndex[
                            findingId
                        ] || 0;


                var selected =
                    active
                    && String(
                        pdfPreviewState
                            .selectedFindingId
                    )
                    === String(
                        findingId
                    )
                    && Number(
                        box.dataset
                            .occurrenceIndex
                    )
                    === selectedOccurrence;


                box.classList.toggle(
                    'is-selected',
                    selected
                );


                var isSignature =
                    finding.entity_type
                        === 'PDF_SIGNATURE';


                box.classList.toggle(
                    'is-signature',
                    isSignature
                );


                var outputMode =
                    (
                        pdfPreviewState
                            .previewMode
                        === 'output'
                    )
                    && !isSignature;


                box.classList.toggle(
                    'is-output-preview',
                    outputMode
                );


                if (outputMode) {

                    box.textContent =
                        finding.marker
                        || '[DANE]';

                } else if (
                    isSignature
                ) {

                    box.textContent =
                        'Podpis cyfrowy';

                } else {

                    box.textContent =
                        '';
                }
            }
        );
    }


    // =========================================================
    // Prawy panel findings
    // =========================================================

    function findXlsxCellByManualEntry(entry) {
        if (!entry || !entry.xlsx_part || !entry.xlsx_cell || !pdfViewerElement) {
            return null;
        }

        var cell = null;
        pdfViewerElement.querySelectorAll('.xlsx-preview-cell').forEach(function (item) {
            if (!cell && item.getAttribute('data-xlsx-part') === entry.xlsx_part && item.getAttribute('data-xlsx-cell') === entry.xlsx_cell) {
                cell = item;
            }
        });

        return cell;
    }

    function activateXlsxSheetForCell(cell) {
        if (!cell || !pdfViewerElement) {
            return;
        }

        var panel = cell.closest('.xlsx-sheet-panel');
        if (!panel) {
            return;
        }

        var sheetName = panel.getAttribute('data-sheet-name');
        if (!sheetName) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-sheet-tab').forEach(function (tab) {
            tab.classList.toggle('is-active', tab.getAttribute('data-sheet-name') === sheetName);
        });

        pdfViewerElement.querySelectorAll('.xlsx-sheet-panel').forEach(function (item) {
            item.classList.toggle('is-active', item === panel);
        });
    }

    function scrollManualSidebarToSelection() {
        if (!pdfFindingsList || (!isSelectedFileXlsx() && !isSelectedFileDocx())) {
            return;
        }

        var selectedItem = pdfFindingsList.querySelector('.pdf-manual-item.is-selected');
        if (!selectedItem) {
            return;
        }

        requestAnimationFrame(function () {
            selectedItem.scrollIntoView({
                block: 'nearest',
                behavior: 'smooth'
            });
        });
    }

    function focusManualXlsxFinding(manualId) {
        if (!manualId || !pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        clearXlsxSelectionStateForMode('manual');

        var manualFinding = getCurrentManualFindings().find(function (entry) {
            return String(entry.id) === String(manualId);
        });

        if (!manualFinding) {
            return;
        }

        var targetCell = findXlsxCellByManualEntry(manualFinding);
        if (!targetCell) {
            return;
        }

        pdfPreviewState.selectedManualFindingId = String(manualId);
        syncSelectedXlsxManualMarks();
        activateXlsxSheetForCell(targetCell);

        var container = pdfViewerContainer || pdfViewerElement;
        if (container && typeof targetCell.getBoundingClientRect === 'function') {
            var targetRect = targetCell.getBoundingClientRect();
            var containerRect = container.getBoundingClientRect();
            var targetScrollTop = container.scrollTop + (targetRect.top - containerRect.top) - (containerRect.height * 0.35);
            container.scrollTo({
                top: Math.max(0, targetScrollTop),
                behavior: 'smooth'
            });
        } else {
            targetCell.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }

        renderPdfFindingsSidebar();
        requestAnimationFrame(scrollManualSidebarToSelection);
    }

    function renderPdfFindingsSidebar() {

        if (!pdfFindingsList) {
            return;
        }


        var html = '';

        if (isSelectedFileXlsx() || isSelectedFileDocx()) {
            var manualFindings = getCurrentManualFindings();
            var selectedText = isSelectedFileXlsx()
                ? (xlsxSelectionState.text || '')
                : (docxSelectionState.text || '');
            var manualAddButtonId = isSelectedFileXlsx()
                ? 'manual-xlsx-add-button'
                : 'manual-docx-add-button';
            html += '<div class="pdf-manual-section">';
            html += '<div class="pdf-manual-header">';
            html += '<span>Dodane ręcznie</span>';
            html += '<span>' + manualFindings.length + '</span>';
            html += '</div>';
            html += '<div class="pdf-manual-body">';

            if (selectedText) {
                html += '<div class="pdf-manual-selection">';
                html += '<div class="pdf-manual-value">' + escapeHtml(selectedText) + '</div>';
                    html += '<button type="button" id="' + manualAddButtonId + '" class="btn btn-primary btn-sm">Dodaj zaznaczenie</button>';
                html += '</div>';
            }

            if (!manualFindings.length) {
                if (!selectedText) {
                    html += '<div class="pdf-manual-empty">Zaznacz tekst w komórce, a następnie kliknij "Dodaj zaznaczenie".</div>';
                }
            } else {
                manualFindings.forEach(function (manualFinding) {
                    var manualId = manualFinding.id;
                    var selectedManual = String(pdfPreviewState.selectedManualFindingId || '') === String(manualId);
                    html += '<div class="pdf-manual-item' + (selectedManual ? ' is-selected' : '') + '" data-manual-id="' + escapeHtml(String(manualId)) + '">';
                    html += '<div class="pdf-manual-info">';
                    html += '<span class="pdf-manual-label">' + escapeHtml(manualFinding.entity_type || 'Zaznaczenie') + '</span>';
                    html += '<span class="pdf-manual-value">' + escapeHtml(manualFinding.raw_value || '') + '</span>';
                    html += '</div>';
                    html += '<button type="button" class="btn btn-danger btn-sm pdf-manual-remove" data-manual-id="' + escapeHtml(String(manualId)) + '">Usuń</button>';
                    html += '</div>';
                });
            }

            html += '</div>';
            html += '</div>';
        }


        currentFindings.forEach(
            function (finding) {

                var occurrences =
                    getFindingOccurrences(
                        finding
                    );


                var current =
                    pdfPreviewState
                        .occurrenceIndex[
                            finding.id
                        ] || 0;


                if (
                    current
                    >= occurrences.length
                ) {
                    current = 0;
                }


                pdfPreviewState
                    .occurrenceIndex[
                        finding.id
                    ] =
                    current;


                var selected =
                    String(
                        pdfPreviewState
                            .selectedFindingId
                    )
                    === String(
                        finding.id
                    );


                var entityLabel =
                    finding.entity_type
                        === 'PDF_SIGNATURE'
                    ? 'Podpis cyfrowy'
                    : finding.entity_type;


                var value =
                    finding.entity_type
                        === 'PDF_SIGNATURE'
                    ? 'Podpis cyfrowy'
                    : (
                        finding.raw_value
                        || finding.marker
                        || 'Wykryty element'
                    );


                var sidebarId =
                    'pdf-side-toggle-'
                    + String(
                        finding.id
                    );


                html +=
                    '<div '
                    + 'class="pdf-finding-item'
                    + (
                        selected
                        ? ' is-selected'
                        : ''
                    )
                    + '">';


                html +=
                    '<button '
                    + 'type="button" '
                    + 'class="pdf-finding-jump" '
                    + 'data-finding-id="'
                    + escapeHtml(
                        String(
                            finding.id
                        )
                    )
                    + '">';


                html +=
                    '<span class="pdf-finding-type">'
                    + escapeHtml(
                        entityLabel || ''
                    )
                    + '</span>';


                html +=
                    '<span class="pdf-finding-value">'
                    + escapeHtml(
                        value
                    )
                    + '</span>';


                if (
                    finding.marker
                    && finding.entity_type
                        !== 'PDF_SIGNATURE'
                ) {
                    html +=
                        '<span class="pdf-finding-marker">'
                        + escapeHtml(
                            finding.marker
                        )
                        + '</span>';
                }


                html +=
                    '</button>';


                html +=
                    '<div class="pdf-finding-controls">';


                html +=
                    '<button '
                    + 'type="button" '
                    + 'class="btn btn-secondary btn-sm '
                    + 'pdf-occurrence-prev" '
                    + 'data-finding-id="'
                    + finding.id
                    + '"'
                    + (
                        occurrences.length < 2
                        ? ' disabled'
                        : ''
                    )
                    + '>'
                    + '‹'
                    + '</button>';


                html +=
                    '<span class="pdf-occurrence-counter">'
                    + (
                        occurrences.length
                        ? current + 1
                        : 0
                    )
                    + ' / '
                    + occurrences.length
                    + '</span>';


                html +=
                    '<button '
                    + 'type="button" '
                    + 'class="btn btn-secondary btn-sm '
                    + 'pdf-occurrence-next" '
                    + 'data-finding-id="'
                    + finding.id
                    + '"'
                    + (
                        occurrences.length < 2
                        ? ' disabled'
                        : ''
                    )
                    + '>'
                    + '›'
                    + '</button>';


                html +=
                    '<label class="pdf-sidebar-anonymize">';

                html +=
                    '<span>Anonimizuj</span>';

                html +=
                    '<div class="checkbox-wrapper-6">';

                html +=
                    '<input '
                    + 'class="tgl tgl-light '
                    + 'pdf-sidebar-toggle" '
                    + 'id="'
                    + sidebarId
                    + '" '
                    + 'type="checkbox" '
                    + 'data-finding-id="'
                    + finding.id
                    + '" '
                    + (
                        isFindingActive(
                            finding.id
                        )
                        ? 'checked'
                        : ''
                    )
                    + '>';

                html +=
                    '<label '
                    + 'class="tgl-btn" '
                    + 'for="'
                    + sidebarId
                    + '"></label>';

                html +=
                    '</div>';

                html +=
                    '</label>';

                html +=
                    '</div>';

                html +=
                    '</div>';
            }
        );


        pdfFindingsList.innerHTML =
            html;

        var manualAddButton = pdfFindingsList.querySelector('#manual-xlsx-add-button, #manual-docx-add-button');
        if (manualAddButton) {
            manualAddButton.addEventListener('click', function () {
                if (isSelectedFileXlsx()) {
                    confirmManualXlsxSelection();
                } else {
                    confirmManualDocxSelection();
                }
            });
        }

        if (isSelectedFileXlsx()) {
            refreshXlsxManualHighlights();
            requestAnimationFrame(scrollManualSidebarToSelection);
        }


        var jumpButtons =
            pdfFindingsList.querySelectorAll(
                '.pdf-finding-jump'
            );


        jumpButtons.forEach(
            function (button) {

                button.addEventListener(
                    'click',
                    function () {

                        focusPdfFinding(
                            button.dataset
                                .findingId
                        );

                        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                            if (
                                isSelectedFileDocx()
                                && modalIsOpen
                                && (pdfPreviewState.previewMode || 'detections') === 'output'
                            ) {
                                openDocxPreview(pdfPreviewState.selectedFindingId);
                            } else {
                                refreshDocxPreviewState();
                            }
                        }
                    }
                );
            }
        );


        var toggles =
            pdfFindingsList.querySelectorAll(
                '.pdf-sidebar-toggle'
            );


        toggles.forEach(
            function (checkbox) {

                checkbox.addEventListener(
                    'change',
                    function () {

                        setFindingActive(
                            checkbox.dataset
                                .findingId,

                            checkbox.checked
                        );

                        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                            refreshDocxPreviewState();
                        }
                    }
                );
            }
        );

        var manualItems = pdfFindingsList.querySelectorAll('.pdf-manual-item');
        manualItems.forEach(function (item) {
            item.addEventListener('click', function (event) {
                if (event.target.closest('.pdf-manual-toggle') || event.target.closest('.pdf-manual-remove')) {
                    return;
                }
                var manualId = item.getAttribute('data-manual-id');
                if (manualId) {
                    if (isSelectedFileXlsx()) {
                        focusManualXlsxFinding(manualId);
                    } else {
                        focusManualDocxFinding(manualId);
                    }
                }
            });
        });

        var manualToggles = pdfFindingsList.querySelectorAll('.pdf-manual-toggle');
        manualToggles.forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                var manualId = checkbox.getAttribute('data-manual-id');
                var manualFindings = getCurrentManualFindings();
                var item = manualFindings.find(function (entry) {
                    return String(entry.id) === String(manualId);
                });
                if (item) {
                    item.enabled = checkbox.checked;
                }
            });
        });

        var manualRemoveButtons = pdfFindingsList.querySelectorAll('.pdf-manual-remove');
        manualRemoveButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                removeManualFindingById(button.getAttribute('data-manual-id'));
            });
        });


        var prevButtons =
            pdfFindingsList.querySelectorAll(
                '.pdf-occurrence-prev'
            );


        prevButtons.forEach(
            function (button) {

                button.addEventListener(
                    'click',
                    function () {

                        movePdfOccurrence(
                            button.dataset
                                .findingId,
                            -1
                        );

                        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                            refreshDocxPreviewState();
                        }
                    }
                );
            }
        );


        var nextButtons =
            pdfFindingsList.querySelectorAll(
                '.pdf-occurrence-next'
            );


        nextButtons.forEach(
            function (button) {

                button.addEventListener(
                    'click',
                    function () {

                        movePdfOccurrence(
                            button.dataset
                                .findingId,
                            1
                        );

                        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                            refreshDocxPreviewState();
                        }
                    }
                );
            }
        );
    }

    function getPdfOverlayAtPoint(
        clientX,
        clientY
    ) {

        if (!pdfViewerElement) {
            return null;
        }


        var boxes =
            pdfViewerElement
                .querySelectorAll(
                    '.pii-overlay-box'
                    + ':not(.is-hidden)'
                );


        // Od końca, ponieważ przy nachodzących
        // boxach interesuje nas ten narysowany
        // najwyżej.

        for (
            var i =
                boxes.length - 1;
            i >= 0;
            i -= 1
        ) {

            var box =
                boxes[i];


            var rect =
                box.getBoundingClientRect();


            var inside =
                clientX >= rect.left
                && clientX <= rect.right
                && clientY >= rect.top
                && clientY <= rect.bottom;


            if (inside) {
                return box;
            }
        }


        return null;
    }

    function selectPdfFindingFromOverlay(
        findingId,
        occurrenceIndex
    ) {

        var finding =
            getFindingById(
                findingId
            );


        if (!finding) {
            return;
        }


        var occurrences =
            getFindingOccurrences(
                finding
            );


        var index =
            Number(
                occurrenceIndex
            );


        if (
            !Number.isInteger(
                index
            )
            || index < 0
            || index >= occurrences.length
        ) {
            return;
        }


        // Zapamiętujemy dokładnie kliknięte
        // wystąpienie findingu.

        pdfPreviewState
            .occurrenceIndex[
                findingId
            ] =
            index;


        pdfPreviewState
            .selectedFindingId =
            findingId;


        // Aktualizujemy sidebar.
        //
        // Ta funkcja odbuduje również licznik,
        // np. 2 / 4.

        renderPdfFindingsSidebar();


        // Aktualizujemy czerwone / niebieskie
        // obramowania na PDF.

        refreshPdfOverlayState();


        // Jeżeli finding jest poza widocznym
        // fragmentem sidebara, przewijamy
        // WYŁĄCZNIE sidebar.

        requestAnimationFrame(
            function () {
                scrollPdfSidebarToFinding(
                    findingId
                );
            }
        );
    }

    function scrollPdfSidebarToFinding(
        findingId
    ) {

        if (!pdfFindingsList) {
            return;
        }


        var buttons =
            pdfFindingsList.querySelectorAll(
                '.pdf-finding-jump'
            );


        var targetItem =
            null;


        buttons.forEach(
            function (button) {

                if (
                    String(
                        button.dataset.findingId
                    )
                    === String(
                        findingId
                    )
                ) {

                    targetItem =
                        button.closest(
                            '.pdf-finding-item'
                        );
                }
            }
        );


        if (!targetItem) {
            return;
        }


        var listRect =
            pdfFindingsList
                .getBoundingClientRect();


        var itemRect =
            targetItem
                .getBoundingClientRect();


        var margin =
            8;


        // Finding jest już w całości widoczny.
        // Nie ruszamy sidebara.

        var fullyVisible =
            itemRect.top
                >= listRect.top
                    + margin
            &&
            itemRect.bottom
                <= listRect.bottom
                    - margin;


        if (fullyVisible) {
            return;
        }


        // Finding jest poza widocznym obszarem.
        // Ustawiamy go mniej więcej na środku
        // prawego panelu.

        var targetTop =
            pdfFindingsList.scrollTop
            + (
                itemRect.top
                - listRect.top
            )
            - (
                pdfFindingsList
                    .clientHeight
                / 2
            )
            + (
                itemRect.height
                / 2
            );


        pdfFindingsList.scrollTo({
            top: Math.max(
                0,
                targetTop
            ),

            behavior:
                'smooth'
        });
    }

    if (pdfViewerContainer) {

        pdfViewerContainer
            .addEventListener(
                'click',
                function (event) {

                    if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                        var hit = event.target.closest('.docx-hit, .xlsx-hit');
                        if (hit) {
                            var id = hit.dataset.docxFindingId || hit.dataset.xlsxFindingId;
                            if (id) {
                                focusDocxFinding(id);
                            }
                        }
                        return;
                    }

                    var clickedBox =
                        getPdfOverlayAtPoint(
                            event.clientX,
                            event.clientY
                        );


                    if (!clickedBox) {
                        return;
                    }


                    selectPdfFindingFromOverlay(
                        clickedBox
                            .dataset
                            .findingId,

                        clickedBox
                            .dataset
                            .occurrenceIndex
                    );
                }
            );

                pdfViewerContainer
            .addEventListener(
                'mousemove',
                function (event) {

                    if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                        return;
                    }

                    var hoveredBox =
                        getPdfOverlayAtPoint(
                            event.clientX,
                            event.clientY
                        );


                    pdfViewerContainer
                        .classList
                        .toggle(
                            'is-over-pii',
                            Boolean(
                                hoveredBox
                            )
                        );
                }
            );


        pdfViewerContainer
            .addEventListener(
                'mouseleave',
                function () {

                    if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                        return;
                    }

                    pdfViewerContainer
                        .classList
                        .remove(
                            'is-over-pii'
                        );
                }
            );
    }

    // =========================================================
    // Nawigacja po wystąpieniach
    // =========================================================

    function movePdfOccurrence(
        findingId,
        direction
    ) {

        var finding =
            getFindingById(
                findingId
            );


        var occurrences =
            getFindingOccurrences(
                finding
            );


        if (!occurrences.length) {
            return;
        }


        var current =
            pdfPreviewState
                .occurrenceIndex[
                    findingId
                ] || 0;


        current =
            (
                current
                + direction
                + occurrences.length
            )
            % occurrences.length;


        pdfPreviewState
            .occurrenceIndex[
                findingId
            ] =
            current;


        focusPdfFinding(
            findingId
        );
    }


    function focusDocxFinding(
        findingId
    ) {
        var finding =
            getFindingById(
                findingId
            );

        if (!finding || !pdfViewerElement) {
            return;
        }

        var occurrences =
            getFindingOccurrences(
                finding
            );

        var current =
            pdfPreviewState
                .occurrenceIndex[
                    findingId
                ] || 0;

        if (occurrences.length) {
            if (current >= occurrences.length) {
                current = 0;
            }
            pdfPreviewState.occurrenceIndex[findingId] = current;
        }

        clearXlsxSelectionStateForMode('auto');
        pdfPreviewState.selectedFindingId = findingId;
        pdfPreviewState.selectedManualFindingId = null;
        renderPdfFindingsSidebar();

        requestAnimationFrame(function () {
            scrollPdfSidebarToFinding(findingId);
        });

        pdfViewerElement.querySelectorAll('.docx-hit, .xlsx-hit').forEach(function (hit) {
            if (!hit.classList.contains('xlsx-manual-hit')) {
                hit.classList.remove('is-selected');
            }
        });

        if (isSelectedFileXlsx()) {
            pdfViewerElement.querySelectorAll('.xlsx-hit.xlsx-manual-hit').forEach(function (hit) {
                hit.classList.remove('is-selected');
            });
        }

        var docxHits = Array.from(
            pdfViewerElement.querySelectorAll(
                '.docx-hit[data-docx-finding-id="' + String(findingId) + '"], .xlsx-hit[data-xlsx-finding-id="' + String(findingId) + '"]'
            )
        );

        if (docxHits.length) {
            var activeIndex = Math.min(
                current,
                docxHits.length - 1
            );
            var hit = docxHits[activeIndex];
            if (hit) {
                activateXlsxSheetForHit(hit);
                hit.classList.add('is-selected');

                if (pdfViewerContainer && typeof hit.getBoundingClientRect === 'function') {
                    var hitRect = hit.getBoundingClientRect();
                    var containerRect = pdfViewerContainer.getBoundingClientRect();
                    var targetScrollTop = pdfViewerContainer.scrollTop + (hitRect.top - containerRect.top) - (containerRect.height * 0.35);

                    pdfViewerContainer.scrollTo({
                        top: Math.max(0, targetScrollTop),
                        behavior: 'smooth'
                    });
                } else {
                    hit.scrollIntoView({
                        block: 'nearest',
                        behavior: 'smooth'
                    });
                }
            }
        }
    }

    function activateXlsxSheetForHit(hit) {
        if (!hit || !hit.classList.contains('xlsx-hit')) {
            return;
        }

        var panel = hit.closest('.xlsx-sheet-panel');
        if (!panel) {
            return;
        }

        var sheetName = panel.getAttribute('data-sheet-name');
        if (!sheetName) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-sheet-tab').forEach(function (tab) {
            tab.classList.toggle('is-active', tab.getAttribute('data-sheet-name') === sheetName);
        });

        pdfViewerElement.querySelectorAll('.xlsx-sheet-panel').forEach(function (item) {
            item.classList.toggle('is-active', item === panel);
        });
    }

    function focusPdfFinding(
        findingId
    ) {

        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
            focusDocxFinding(findingId);
            return;
        }

        var finding =
            getFindingById(
                findingId
            );


        var occurrences =
            getFindingOccurrences(
                finding
            );


        if (
            !finding
            || !occurrences.length
            || !pdfPreviewState.viewer
        ) {
            return;
        }


        var current =
            pdfPreviewState
                .occurrenceIndex[
                    findingId
                ] || 0;


        if (
            current
            >= occurrences.length
        ) {
            current = 0;
        }


        pdfPreviewState
            .occurrenceIndex[
                findingId
            ] =
            current;


        pdfPreviewState
            .selectedFindingId =
            findingId;


        renderPdfFindingsSidebar();

        refreshPdfOverlayState();


        // Nie ustawiamy currentPageNumber.
        //
        // To właśnie powodowało nagły skok
        // PDF.js do początku strony.
        //
        // Przewijamy wyłącznie wewnętrzny
        // scroll kontenera PDF.

        requestAnimationFrame(
            function () {
                scrollToSelectedPdfBox();
            }
        );
    }


    function scrollToSelectedPdfBox() {

        var findingId =
            pdfPreviewState
                .selectedFindingId;


        if (
            !findingId
            || !pdfViewerElement
            || !pdfViewerContainer
            || !pdfPreviewState.viewer
        ) {
            return;
        }


        var finding =
            getFindingById(
                findingId
            );


        var occurrences =
            getFindingOccurrences(
                finding
            );


        if (!occurrences.length) {
            return;
        }


        var current =
            pdfPreviewState
                .occurrenceIndex[
                    findingId
                ] || 0;


        if (
            current
            >= occurrences.length
        ) {
            current = 0;
        }


        var occurrence =
            occurrences[
                current
            ];


        // -----------------------------------------------------
        // Najlepszy przypadek:
        // overlay jest już wyrenderowany.
        // -----------------------------------------------------

        var selector =
            '.pii-overlay-box'
            + '[data-finding-id="'
            + findingId
            + '"]'
            + '[data-occurrence-index="'
            + current
            + '"]';


        var box =
            pdfViewerElement.querySelector(
                selector
            );


        var containerRect =
            pdfViewerContainer
                .getBoundingClientRect();


        if (box) {

            var boxRect =
                box.getBoundingClientRect();

            var targetTop =
                pdfViewerContainer.scrollTop
                + (
                    boxRect.top
                    - containerRect.top
                )
                - (
                    pdfViewerContainer
                        .clientHeight
                    / 2
                )
                + (
                    boxRect.height
                    / 2
                );


            var targetLeft =
                pdfViewerContainer.scrollLeft
                + (
                    boxRect.left
                    - containerRect.left
                )
                - (
                    pdfViewerContainer
                        .clientWidth
                    / 2
                )
                + (
                    boxRect.width
                    / 2
                );


            pdfViewerContainer.scrollTo({
                top: Math.max(
                    0,
                    targetTop
                ),

                left: Math.max(
                    0,
                    targetLeft
                ),

                behavior: 'smooth'
            });


            return;
        }


        // -----------------------------------------------------
        // Fallback:
        //
        // Przy dużym PDF dana strona może jeszcze nie mieć
        // wyrenderowanego overlayu.
        //
        // Wtedy przewijamy płynnie bezpośrednio do
        // współrzędnych pdf_bbox na właściwej stronie.
        // -----------------------------------------------------

        var pageIndex =
            Number(
                occurrence.page
            );


        if (
            !Number.isFinite(
                pageIndex
            )
            || pageIndex < 0
        ) {
            return;
        }


        var pageView =
            pdfPreviewState
                .viewer
                .getPageView(
                    pageIndex
                );


        if (
            !pageView
            || !pageView.div
        ) {
            return;
        }


        var pageRect =
            pageView.div
                .getBoundingClientRect();


        var targetTop =
            pdfViewerContainer.scrollTop
            + (
                pageRect.top
                - containerRect.top
            );

        var targetLeft =
            pdfViewerContainer.scrollLeft
            + (
                pageRect.left
                - containerRect.left
            );


        if (
            pageView.viewport
            && Array.isArray(
                occurrence.pdf_bbox
            )
            && occurrence
                .pdf_bbox
                .length === 4
        ) {

            var pdfBox =
                occurrence.pdf_bbox;


            var point1 =
                pageView.viewport
                    .convertToViewportPoint(
                        pdfBox[0],
                        pdfBox[1]
                    );

            var point2 =
                pageView.viewport
                    .convertToViewportPoint(
                        pdfBox[2],
                        pdfBox[3]
                    );

            var boxTop =
                Math.min(
                    point1[1],
                    point2[1]
                );

            var boxHeight =
                Math.abs(
                    point2[1]
                    - point1[1]
                );

            var boxLeft =
                Math.min(
                    point1[0],
                    point2[0]
                );

            var boxWidth =
                Math.abs(
                    point2[0]
                    - point1[0]
                );


            targetTop +=
                boxTop
                - (
                    pdfViewerContainer
                        .clientHeight
                    / 2
                )
                + (
                    boxHeight
                    / 2
                );

            targetLeft +=
                boxLeft
                - (
                    pdfViewerContainer
                        .clientWidth
                    / 2
                )
                + (
                    boxWidth
                    / 2
                );
        }


        pdfViewerContainer.scrollTo({
            top: Math.max(
                0,
                targetTop
            ),

            left: Math.max(
                0,
                targetLeft
            ),

            behavior: 'smooth'
        });
    }


    // =========================================================
    // Zoom
    // =========================================================

    function applyXlsxZoom() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        var scale = Number(xlsxZoomState.scale) || 1;
        scale = Math.min(Math.max(scale, 0.5), 2.5);
        xlsxZoomState.scale = scale;

        if (pdfViewerElement) {
            pdfViewerElement.style.zoom = String(scale);
            pdfViewerElement.style.transform = 'none';
        }
    }

    function applyDocxZoom() {
        if (!pdfViewerElement || !isSelectedFileDocx()) {
            return;
        }

        var scale = Number(docxZoomState.scale) || 1;
        scale = Math.min(Math.max(scale, 0.5), 2.5);
        docxZoomState.scale = scale;

        if (pdfViewerElement) {
            pdfViewerElement.style.zoom = String(scale);
            pdfViewerElement.style.transform = 'none';
        }
    }

    function updatePdfZoomValue() {
        if (!pdfZoomValue) {
            return;
        }

        if (pdfPreviewState.viewer && pdfPreviewState.viewer.currentScale && isFinite(pdfPreviewState.viewer.currentScale)) {
            var scale = pdfPreviewState.viewer.currentScale;
            pdfZoomValue.textContent = Math.round(scale * 100) + '%';
            return;
        }

        if (isSelectedFileXlsx()) {
            pdfZoomValue.textContent = Math.round((Number(xlsxZoomState.scale) || 1) * 100) + '%';
            return;
        }

        if (isSelectedFileDocx()) {
            pdfZoomValue.textContent = Math.round((Number(docxZoomState.scale) || 1) * 100) + '%';
        }
    }


    if (pdfZoomInBtn) {
        pdfZoomInBtn.addEventListener(
            'click',
            function () {
                if (pdfPreviewState.viewer) {
                    pdfPreviewState.viewer.currentScale *= 1.15;
                    updatePdfZoomValue();
                    return;
                }

                if (isSelectedFileXlsx()) {
                    xlsxZoomState.scale = Number((Number(xlsxZoomState.scale) || 1) * 1.15);
                    applyXlsxZoom();
                    updatePdfZoomValue();
                    return;
                }

                if (isSelectedFileDocx()) {
                    docxZoomState.scale = Number((Number(docxZoomState.scale) || 1) * 1.15);
                    applyDocxZoom();
                    updatePdfZoomValue();
                }
            }
        );
    }


    if (pdfZoomOutBtn) {
        pdfZoomOutBtn.addEventListener(
            'click',
            function () {
                if (pdfPreviewState.viewer) {
                    pdfPreviewState.viewer.currentScale /= 1.15;
                    updatePdfZoomValue();
                    return;
                }

                if (isSelectedFileXlsx()) {
                    xlsxZoomState.scale = Number((Number(xlsxZoomState.scale) || 1) / 1.15);
                    applyXlsxZoom();
                    updatePdfZoomValue();
                    return;
                }

                if (isSelectedFileDocx()) {
                    docxZoomState.scale = Number((Number(docxZoomState.scale) || 1) / 1.15);
                    applyDocxZoom();
                    updatePdfZoomValue();
                }
            }
        );
    }


    if (pdfZoomFitBtn) {
        pdfZoomFitBtn.addEventListener(
            'click',
            function () {
                if (pdfPreviewState.viewer) {
                    pdfPreviewState.viewer.currentScaleValue = 'page-width';
                    updatePdfZoomValue();
                    return;
                }

                if (isSelectedFileXlsx()) {
                    xlsxZoomState.scale = 1;
                    applyXlsxZoom();
                    updatePdfZoomValue();
                    return;
                }

                if (isSelectedFileDocx()) {
                    docxZoomState.scale = 1;
                    applyDocxZoom();
                    updatePdfZoomValue();
                }
            }
        );
    }


    // =========================================================
    // Wykrycia / Po anonimizacji
    // =========================================================

    function setPreviewMode(
        mode
    ) {

        if (isSelectedFileXlsx()) {
            pdfPreviewState.activeXlsxSheetName = getActiveXlsxSheetName();
        }

        pdfPreviewState.previewMode =
            mode === 'output'
            ? 'output'
            : 'detections';


        if (previewModeDetectionsBtn) {

            previewModeDetectionsBtn
                .classList.toggle(
                    'is-active',

                    pdfPreviewState
                        .previewMode
                        === 'detections'
                );
        }


        if (previewModeOutputBtn) {

            previewModeOutputBtn
                .classList.toggle(
                    'is-active',

                    pdfPreviewState
                        .previewMode
                        === 'output'
                );
        }

        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
            if (modalIsOpen) {
                var currentSheet = isSelectedFileXlsx() ? getActiveXlsxSheetName() : null;
                openDocxPreview(
                    pdfPreviewState.selectedFindingId
                );
                if (isSelectedFileXlsx() && currentSheet) {
                    requestAnimationFrame(function () {
                        applyActiveXlsxSheet(currentSheet);
                    });
                }
            } else {
                var currentSheetBeforeRefresh = isSelectedFileXlsx() ? getActiveXlsxSheetName() : null;
                refreshDocxPreviewState();
                if (isSelectedFileXlsx() && currentSheetBeforeRefresh) {
                    requestAnimationFrame(function () {
                        applyActiveXlsxSheet(currentSheetBeforeRefresh);
                    });
                }
            }
            return;
        }

        refreshPdfOverlayState();
    }


    if (previewModeDetectionsBtn) {

        previewModeDetectionsBtn
            .addEventListener(
                'click',
                function () {

                    setPreviewMode(
                        'detections'
                    );
                }
            );
    }


    if (previewModeOutputBtn) {

        previewModeOutputBtn
            .addEventListener(
                'click',
                function () {

                    setPreviewMode(
                        'output'
                    );
                }
            );
    }


    // =========================================================
    // Wyszukiwanie
    // =========================================================

    function mergeAdjacentTextNodes(parent) {
        if (!parent || !parent.childNodes) {
            return;
        }

        var previousTextNode = null;
        var children = Array.prototype.slice.call(parent.childNodes);

        children.forEach(function (child) {
            if (child.nodeType === Node.TEXT_NODE) {
                if (previousTextNode) {
                    previousTextNode.textContent += child.textContent || '';
                    parent.removeChild(child);
                    return;
                }
                previousTextNode = child;
                return;
            }

            previousTextNode = null;
        });
    }

    function clearXlsxSearchHighlights() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-hit.is-search-match, .xlsx-hit.is-search-first-match').forEach(function (hit) {
            if (!hit.parentNode) {
                return;
            }

            if (hit.dataset.xlsxFindingId || hit.dataset.manualFindingId) {
                hit.classList.remove('is-search-match');
                hit.classList.remove('is-search-first-match');
                return;
            }

            var textNode = document.createTextNode(hit.textContent || '');
            hit.parentNode.replaceChild(textNode, hit);
        });

        pdfViewerElement.querySelectorAll('.xlsx-preview-cell').forEach(function (cell) {
            mergeAdjacentTextNodes(cell);
        });
    }

    function getXlsxSearchHitList() {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return [];
        }

        var hits = [];
        pdfViewerElement.querySelectorAll('.xlsx-sheet-panel').forEach(function (sheetPanel) {
            sheetPanel.querySelectorAll('.xlsx-hit.is-search-match').forEach(function (hit) {
                hits.push(hit);
            });
        });

        return hits;
    }

    function focusXlsxSearchHit(hit) {
        if (!hit || !pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        pdfViewerElement.querySelectorAll('.xlsx-hit.is-search-match').forEach(function (currentHit) {
            currentHit.classList.remove('is-search-first-match');
        });

        hit.classList.add('is-search-first-match');
        activateXlsxSheetForHit(hit);

        if (pdfViewerContainer && typeof hit.getBoundingClientRect === 'function') {
            var hitRect = hit.getBoundingClientRect();
            var containerRect = pdfViewerContainer.getBoundingClientRect();
            var targetScrollTop = pdfViewerContainer.scrollTop + (hitRect.top - containerRect.top) - (containerRect.height * 0.35);

            pdfViewerContainer.scrollTo({
                top: Math.max(0, targetScrollTop),
                behavior: 'smooth'
            });
        } else if (typeof hit.scrollIntoView === 'function') {
            hit.scrollIntoView({
                block: 'nearest',
                behavior: 'smooth'
            });
        }
    }

    function moveXlsxSearchCursor(findPrevious) {
        var hits = getXlsxSearchHitList();
        if (!hits.length) {
            xlsxSearchState.hits = [];
            xlsxSearchState.currentIndex = -1;
            return;
        }

        var currentHit = pdfViewerElement.querySelector('.xlsx-hit.is-search-first-match');
        var activeIndex = currentHit ? hits.indexOf(currentHit) : xlsxSearchState.currentIndex;

        if (activeIndex < 0 || activeIndex >= hits.length) {
            activeIndex = findPrevious ? hits.length - 1 : 0;
        } else {
            activeIndex = (activeIndex + (findPrevious ? -1 : 1) + hits.length) % hits.length;
        }

        xlsxSearchState.hits = hits;
        xlsxSearchState.currentIndex = activeIndex;
        focusXlsxSearchHit(hits[activeIndex]);
    }

    function wrapXlsxTextNodeMatches(node, query) {
        if (!node || !query) {
            return;
        }

        var value = node.nodeValue || '';
        var lowerValue = value.toLowerCase();
        var queryLower = String(query).toLowerCase();
        if (!queryLower) {
            return;
        }

        var matchIndex = lowerValue.indexOf(queryLower);
        if (matchIndex < 0) {
            return;
        }

        var parent = node.parentNode;
        if (!parent || parent.closest('.xlsx-hit')) {
            return;
        }

        var cursor = 0;
        var fragment = document.createDocumentFragment();

        while (matchIndex >= 0) {
            if (matchIndex > cursor) {
                fragment.appendChild(document.createTextNode(value.slice(cursor, matchIndex)));
            }

            var mark = document.createElement('mark');
            mark.className = 'xlsx-hit is-search-match';
            mark.textContent = value.slice(matchIndex, matchIndex + queryLower.length);
            fragment.appendChild(mark);

            cursor = matchIndex + queryLower.length;
            matchIndex = lowerValue.indexOf(queryLower, cursor);
        }

        if (cursor < value.length) {
            fragment.appendChild(document.createTextNode(value.slice(cursor)));
        }

        parent.replaceChild(fragment, node);
    }

    function applyXlsxSearch(query) {
        if (!pdfViewerElement || !isSelectedFileXlsx()) {
            return;
        }

        clearXlsxSearchHighlights();

        var q = (query || '').trim();
        if (!q) {
            return;
        }

        var qLower = q.toLowerCase();

        pdfViewerElement.querySelectorAll('.xlsx-preview-cell').forEach(function (cell) {
            var walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT, function (textNode) {
                var parent = textNode.parentElement;
                if (!parent || parent.closest('.xlsx-hit')) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            });

            var textNodes = [];
            while (walker.nextNode()) {
                textNodes.push(walker.currentNode);
            }

            textNodes.forEach(function (textNode) {
                if ((textNode.nodeValue || '').toLowerCase().indexOf(qLower) !== -1) {
                    wrapXlsxTextNodeMatches(textNode, qLower);
                }
            });

            mergeAdjacentTextNodes(cell);
        });

        pdfViewerElement.querySelectorAll('.xlsx-sheet-panel').forEach(function (sheetPanel) {
            var firstHit = sheetPanel.querySelector('.xlsx-hit.is-search-match');
            if (!firstHit) {
                return;
            }

            firstHit.classList.add('is-search-first-match');
        });

        var allHits = getXlsxSearchHitList();
        xlsxSearchState.hits = allHits;
        xlsxSearchState.currentIndex = allHits.length ? 0 : -1;

        if (allHits.length) {
            focusXlsxSearchHit(allHits[0]);
        }
    }

    function clearDocxSearchHighlights() {
        if (!pdfViewerElement || !isSelectedFileDocx()) {
            return;
        }

        pdfViewerElement.querySelectorAll('.docx-hit.is-search-match, .docx-hit.is-search-first-match').forEach(function (hit) {
            if (!hit.parentNode) {
                return;
            }

            if (hit.dataset.docxFindingId) {
                hit.classList.remove('is-search-match');
                hit.classList.remove('is-search-first-match');
                return;
            }

            var textNode = document.createTextNode(hit.textContent || '');
            hit.parentNode.replaceChild(textNode, hit);
        });

        docxSearchState.hits = [];
        docxSearchState.currentIndex = -1;
    }

    function rebuildDocxSearchMatches(query) {
        if (!pdfViewerElement || !isSelectedFileDocx()) {
            return;
        }

        var q = (query || '').trim();
        if (!q) {
            clearDocxSearchHighlights();
            return;
        }

        var baseHtml = pdfViewerElement.dataset.docxOriginalHtml || pdfViewerElement.innerHTML;
        var root = document.createElement('div');
        root.innerHTML = baseHtml;

        var qLower = q.toLowerCase();
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, function (textNode) {
            var parent = textNode.parentElement;
            if (!parent || parent.closest('.docx-hit, .xlsx-hit, style, script')) {
                return NodeFilter.FILTER_REJECT;
            }
            return NodeFilter.FILTER_ACCEPT;
        });

        var textNodes = [];
        while (walker.nextNode()) {
            textNodes.push(walker.currentNode);
        }

        textNodes.forEach(function (textNode) {
            if ((textNode.nodeValue || '').toLowerCase().indexOf(qLower) === -1) {
                return;
            }

            var value = textNode.nodeValue || '';
            var parent = textNode.parentNode;
            if (!parent || parent.closest('.docx-hit, .xlsx-hit, style, script')) {
                return;
            }

            var fragment = document.createDocumentFragment();
            var cursor = 0;
            var matchIndex = value.toLowerCase().indexOf(qLower);

            while (matchIndex >= 0) {
                if (matchIndex > cursor) {
                    fragment.appendChild(document.createTextNode(value.slice(cursor, matchIndex)));
                }

                var mark = document.createElement('mark');
                mark.className = 'docx-hit is-search-match';
                mark.textContent = value.slice(matchIndex, matchIndex + qLower.length);
                fragment.appendChild(mark);

                cursor = matchIndex + qLower.length;
                matchIndex = value.toLowerCase().indexOf(qLower, cursor);
            }

            if (cursor < value.length) {
                fragment.appendChild(document.createTextNode(value.slice(cursor)));
            }

            parent.replaceChild(fragment, textNode);
        });

        pdfViewerElement.innerHTML = root.innerHTML;

        var hits = Array.from(pdfViewerElement.querySelectorAll('.docx-hit.is-search-match'));
        docxSearchState.hits = hits;
        docxSearchState.currentIndex = hits.length ? 0 : -1;

        if (!hits.length) {
            return;
        }

        hits.forEach(function (hit) {
            hit.classList.remove('is-search-first-match');
        });

        hits[0].classList.add('is-search-first-match');
        focusDocxSearchHit(hits[0]);
    }

    function focusDocxSearchHit(hit) {
        if (!hit || !pdfViewerElement || !isSelectedFileDocx()) {
            return;
        }

        pdfViewerElement.querySelectorAll('.docx-hit.is-search-first-match').forEach(function (currentHit) {
            currentHit.classList.remove('is-search-first-match');
        });

        hit.classList.add('is-search-first-match');

        var scrollContainer = null;
        if (pdfViewerContainer && pdfViewerContainer.scrollHeight > pdfViewerContainer.clientHeight) {
            scrollContainer = pdfViewerContainer;
        } else if (pdfViewerElement && pdfViewerElement.scrollHeight > pdfViewerElement.clientHeight) {
            scrollContainer = pdfViewerElement;
        }

        if (scrollContainer && typeof hit.getBoundingClientRect === 'function') {
            var hitRect = hit.getBoundingClientRect();
            var containerRect = scrollContainer.getBoundingClientRect();
            var targetScrollTop = scrollContainer.scrollTop + (hitRect.top - containerRect.top) - (containerRect.height * 0.35);

            scrollContainer.scrollTo({
                top: Math.max(0, targetScrollTop),
                behavior: 'smooth'
            });
        } else if (typeof hit.scrollIntoView === 'function') {
            hit.scrollIntoView({
                block: 'nearest',
                behavior: 'smooth'
            });
        }
    }

    function moveDocxSearchCursor(findPrevious) {
        var hits = Array.from(pdfViewerElement.querySelectorAll('.docx-hit.is-search-match'));
        if (!hits.length) {
            docxSearchState.hits = [];
            docxSearchState.currentIndex = -1;
            return;
        }

        var currentHit = pdfViewerElement.querySelector('.docx-hit.is-search-first-match');
        var activeIndex = currentHit ? hits.indexOf(currentHit) : docxSearchState.currentIndex;

        if (activeIndex < 0 || activeIndex >= hits.length) {
            activeIndex = findPrevious ? hits.length - 1 : 0;
        } else {
            activeIndex = (activeIndex + (findPrevious ? -1 : 1) + hits.length) % hits.length;
        }

        docxSearchState.hits = hits;
        docxSearchState.currentIndex = activeIndex;
        focusDocxSearchHit(hits[activeIndex]);
    }

    function applyDocxSearch(query) {
        if (!pdfViewerElement || !pdfSearchInput || !isSelectedFileDocx()) {
            return;
        }

        rebuildDocxSearchMatches(query);
    }

    function dispatchPdfSearch(
        findPrevious,
        type
    ) {

        if (isSelectedFileDocx() || isSelectedFileXlsx()) {
                if (pdfSearchInput) {
                    if (isSelectedFileXlsx()) {
                        var query = (pdfSearchInput.value || '').trim();
                        if (!query) {
                            clearXlsxSearchHighlights();
                            xlsxSearchState.hits = [];
                            xlsxSearchState.currentIndex = -1;
                            return;
                        }

                        if (type === 'again') {
                            moveXlsxSearchCursor(findPrevious);
                            return;
                        }

                        applyXlsxSearch(query);
                    } else {
                        var docxQuery = (pdfSearchInput.value || '').trim();
                        if (!docxQuery) {
                            clearDocxSearchHighlights();
                            return;
                        }

                        if (type === 'again') {
                            moveDocxSearchCursor(findPrevious);
                            return;
                        }

                        applyDocxSearch(docxQuery);
                    }
                }
                return;
            }

        if (
            !pdfPreviewState.eventBus
            || !pdfSearchInput
        ) {
            return;
        }


        pdfPreviewState
            .eventBus
            .dispatch(
                'find',
                {
                    source:
                        pdfSearchInput,

                    type:
                        type || '',

                    query:
                        pdfSearchInput.value,

                    phraseSearch:
                        true,

                    caseSensitive:
                        false,

                    entireWord:
                        false,

                    highlightAll:
                        true,

                    findPrevious:
                        Boolean(
                            findPrevious
                        ),

                    matchDiacritics:
                        true
                }
            );
    }


    if (pdfSearchInput) {

        pdfSearchInput.addEventListener(
            'input',
            function () {

                dispatchPdfSearch(
                    false,
                    ''
                );
            }
        );


        pdfSearchInput.addEventListener(
            'keydown',
            function (event) {

                if (
                    event.key
                    === 'Enter'
                ) {
                    event.preventDefault();

                    dispatchPdfSearch(
                        event.shiftKey,
                        'again'
                    );
                }
            }
        );
    }


    if (pdfSearchPrev) {

        pdfSearchPrev.addEventListener(
            'click',
            function () {

                dispatchPdfSearch(
                    true,
                    'again'
                );
            }
        );
    }


    if (pdfSearchNext) {

        pdfSearchNext.addEventListener(
            'click',
            function () {

                dispatchPdfSearch(
                    false,
                    'again'
                );
            }
        );
    }


    // =========================================================
    // Zamykanie modala / Ctrl+F
    // =========================================================

    if (modalCloseBtn) {

        modalCloseBtn.addEventListener(
            'click',
            closePdfPreview
        );
    }


    window.addEventListener(
        'click',
        function (event) {

            if (
                event.target
                === modal
            ) {
                closePdfPreview();
            }
        }
    );


    document.addEventListener(
        'keydown',
        function (event) {

            if (
                !modal
                || modal.style.display
                    !== 'flex'
            ) {
                return;
            }


            if (
                event.key
                === 'Escape'
            ) {
                closePdfPreview();

                return;
            }


            if (
                (
                    event.ctrlKey
                    || event.metaKey
                )
                && event.key
                    .toLowerCase()
                    === 'f'
            ) {
                event.preventDefault();


                if (pdfSearchInput) {

                    pdfSearchInput.focus();

                    pdfSearchInput.select();
                }
            }
        }
    );
    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(
            document.createTextNode(text)
        );
        return div.innerHTML;
    }

})();