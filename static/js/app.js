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

        previewMode: 'detections'
    };

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
        resetPdfPreview();

        currentFindings = [];

        selectedFile = file;

        findingsDiv.innerHTML = '';

        statusDiv.textContent = '';

        fileInfo.textContent =
            'Wybrany plik: '
            + file.name
            + ' ('
            + formatSize(file.size)
            + ')';

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
        currentFindings =
            findings || [];

        if (currentFindings.length === 0) {
            findingsDiv.innerHTML = '<p>Brak wykrytych danych.</p>';
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

        currentFindings.forEach(function (f) {
            html += '<tr>';
            html += '<td>' + escapeHtml(f.entity_type) + '</td>';
            html += '<td>' + escapeHtml(f.marker) + '</td>';
            html += '<td>' + (f.score.toFixed(2) * 100) + '%</td>';
            // html += '<td>' + escapeHtml(f.reason) + '</td>';
            html += '<td>' + f.count + '</td>';
            html += '<td><div class="checkbox-wrapper-6"><input class="tgl tgl-light" id="cb1-6-' + f.id + '" type="checkbox" name="anonymize" value="' + f.id + '" checked><label class="tgl-btn" for="cb1-6-' + f.id + '"></label></div></td>';
            if (isPdf) {
                // Jeśli PDF, dajemy przycisk Pokaż z podanym numerem strony
                html +=
                    '<td>'
                    + '<button '
                    + 'type="button" '
                    + 'class="btn btn-secondary btn-sm preview-btn" '
                    + 'data-finding-id="' + f.id + '">'
                    + 'Pokaż'
                    + '</button>'
                    + '</td>';
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
                        renderPdfFindingsSidebar();
                        refreshPdfOverlayState();
                    }
                );
            }
        );

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
    }

    function isSelectedFilePdf() {
        return Boolean(
            selectedFile
            && /\.pdf$/i.test(
                selectedFile.name
            )
        );
    }

    function getFindingById(
        findingId
    ) {
        return (
            currentFindings.find(
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

            previewMode: 'detections'
        };


        if (pdfViewerElement) {
            pdfViewerElement.innerHTML =
                '';
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


        setPreviewMode(
            'detections'
        );
    }


    // =========================================================
    // Ładowanie całego PDF
    // =========================================================

    async function ensurePdfPreviewLoaded() {

        if (
            pdfPreviewState.viewer
            && pdfPreviewState.loadedFile
                === selectedFile
        ) {
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

        pdfPreviewState.loadedFile =
            selectedFile;


        // PDF gotowy - pokazujemy wszystkie strony.
        eventBus.on(
            'pagesinit',
            function () {

                viewer.currentScaleValue =
                    'page-width';


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


                updatePdfZoomValue();

                renderPdfFindingsSidebar();
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
                await selectedFile
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
    }


    // =========================================================
    // Otwieranie / zamykanie
    // =========================================================

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

        modal.style.display =
            'none';

        modal.setAttribute(
            'aria-hidden',
            'true'
        );

        document.body.classList.remove(
            'pdf-preview-open'
        );
    }


    // =========================================================
    // Overlay Presidio
    // =========================================================

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


                        var left =
                            Math.min(
                                point1[0],
                                point2[0]
                            );

                        var top =
                            Math.min(
                                point1[1],
                                point2[1]
                            );

                        var width =
                            Math.abs(
                                point2[0]
                                - point1[0]
                            );

                        var height =
                            Math.abs(
                                point2[1]
                                - point1[1]
                            );


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

    function renderPdfFindingsSidebar() {

        if (!pdfFindingsList) {
            return;
        }


        var html = '';


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
                    }
                );
            }
        );


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


    function focusPdfFinding(
        findingId
    ) {

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

    function updatePdfZoomValue() {

        if (
            !pdfPreviewState.viewer
            || !pdfZoomValue
        ) {
            return;
        }


        var scale =
            pdfPreviewState
                .viewer
                .currentScale;


        if (
            scale
            && isFinite(scale)
        ) {
            pdfZoomValue.textContent =
                Math.round(
                    scale * 100
                )
                + '%';
        }
    }


    if (pdfZoomInBtn) {
        pdfZoomInBtn.addEventListener(
            'click',
            function () {

                if (!pdfPreviewState.viewer) {
                    return;
                }

                pdfPreviewState
                    .viewer
                    .currentScale *=
                    1.15;
            }
        );
    }


    if (pdfZoomOutBtn) {
        pdfZoomOutBtn.addEventListener(
            'click',
            function () {

                if (!pdfPreviewState.viewer) {
                    return;
                }

                pdfPreviewState
                    .viewer
                    .currentScale /=
                    1.15;
            }
        );
    }


    if (pdfZoomFitBtn) {
        pdfZoomFitBtn.addEventListener(
            'click',
            function () {

                if (!pdfPreviewState.viewer) {
                    return;
                }

                pdfPreviewState
                    .viewer
                    .currentScaleValue =
                    'page-width';
            }
        );
    }


    // =========================================================
    // Wykrycia / Po anonimizacji
    // =========================================================

    function setPreviewMode(
        mode
    ) {

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

    function dispatchPdfSearch(
        findPrevious,
        type
    ) {

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