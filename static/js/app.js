const state = {
    isLoading: false,
    currentModel: 'BAAI/bge-m3',
    models: ['BAAI/bge-m3'],
    lastCitations: [],
    chatHistory: [],
    personalDocs: [],
    adminDocuments: [],
    adminSummary: {
        document_count: 0,
        active_document_count: 0,
        inactive_document_count: 0,
        today_upload_count: 0
    }
};

function setupPageState() {
    const bodyPage = document.body.dataset.page || 'chat';
    const navButtons = document.querySelectorAll('.nav-item');
    const panels = document.querySelectorAll('.page-panel');

    navButtons.forEach((button) => {
        const isActive = button.dataset.nav === bodyPage;
        button.classList.toggle('active', isActive);
    });

    const pageIdMap = {
        chat: 'pageChat',
        documents: 'pageDocuments',
        admin: 'pageAdmin'
    };

    const currentPage = pageIdMap[bodyPage] || 'pageChat';
    panels.forEach((panel) => {
        panel.classList.toggle('active', panel.id === currentPage);
    });

    const titleMap = {
        chat: 'Chat',
        documents: 'Tài liệu cá nhân',
        admin: 'Admin'
    };
    document.getElementById('pageTitle').textContent = titleMap[bodyPage] || 'Chat';
}

function setupEventListeners() {
    document.getElementById('modelSelect').addEventListener('change', (event) => {
        state.currentModel = event.target.value;
    });

    document.getElementById('sendBtn').addEventListener('click', sendMessage);
    document.getElementById('questionInput').addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey && !state.isLoading) {
            sendMessage();
        }
    });

    document.getElementById('newConversationBtn').addEventListener('click', newConversation);
    document.getElementById('exportBtn').addEventListener('click', exportChat);
    document.getElementById('closeCitationsBtn').addEventListener('click', () => {
        document.getElementById('citationsPanel').style.display = 'none';
    });

    document.querySelectorAll('.nav-item').forEach((item) => {
        item.addEventListener('click', () => {
            const page = item.dataset.nav;
            const routeMap = {
                chat: '/chat',
                documents: '/documents',
                admin: '/admin'
            };
            window.location.href = routeMap[page] || '/chat';
        });
    });

    document.querySelectorAll('.prompt-chip').forEach((chip) => {
        chip.addEventListener('click', () => {
            const input = document.getElementById('questionInput');
            input.value = chip.dataset.question || '';
            input.focus();
        });
    });

    const fileInput = document.getElementById('fileInput');
    const selectFileBtn = document.getElementById('selectFileBtn');
    const dropZone = document.getElementById('dropZone');

    selectFileBtn.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', uploadPersonalDocument);

    dropZone.addEventListener('dragover', (event) => {
        event.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (event) => {
        event.preventDefault();
        dropZone.classList.remove('drag-over');
        if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
            fileInput.files = event.dataTransfer.files;
            uploadPersonalDocument();
        }
    });

    document.getElementById('adminSearch').addEventListener('input', loadAdminDashboard);
    document.getElementById('adminCategoryFilter').addEventListener('change', loadAdminDashboard);
    document.getElementById('adminTypeFilter').addEventListener('change', loadAdminDashboard);
}

function renderWelcomeMessage() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = `
        <div class="welcome-message">
            <h2>Chào mừng đến với Hệ Thống Tra Cứu Tài Liệu Pháp Luật</h2>
            <p>Đặt câu hỏi về pháp luật và nhận câu trả lời dựa trên cơ sở dữ liệu pháp lý.</p>
            <div class="feature-grid">
                <div class="feature"><i class="fas fa-search"></i><span>Tìm kiếm vector</span></div>
                <div class="feature"><i class="fas fa-quote-left"></i><span>Trích dẫn chính xác</span></div>
                <div class="feature"><i class="fas fa-robot"></i><span>Trả lời bằng LLM</span></div>
                <div class="feature"><i class="fas fa-link"></i><span>Liên kết tài liệu</span></div>
            </div>
        </div>
    `;
}

async function loadModels() {
    const modelSelect = document.getElementById('modelSelect');
    modelSelect.innerHTML = state.models.map((model) => `<option value="${model}">${model}</option>`).join('');
    modelSelect.value = state.currentModel;
}

async function loadChatHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        const history = data.history || [];
        state.chatHistory = history;

        if (!history.length) {
            renderWelcomeMessage();
            return;
        }

        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = '';
        history.forEach((entry) => {
            addMessageToChat(entry.question, 'user', entry.timestamp);
            addMessageToChat(entry.response, 'assistant', entry.timestamp);
            if (entry.citations && entry.citations.length) {
                displayCitations(entry.citations);
            }
        });
    } catch (error) {
        console.error('Error loading history:', error);
        renderWelcomeMessage();
    }
}

async function loadConversationList() {
    try {
        const response = await fetch('/api/conversations');
        if (!response.ok) return;
        const data = await response.json();
        const list = document.getElementById('chatHistoryGroups');
        list.innerHTML = '';
        (data.conversations || []).forEach((conversation) => {
            const button = document.createElement('button');
            button.className = 'history-item';
            button.textContent = conversation.question || 'Cuộc trò chuyện';
            button.title = button.textContent;
            button.addEventListener('click', () => loadConversation(conversation.conversation_id));
            list.appendChild(button);
        });
    } catch (error) {
        console.error('Error loading conversations:', error);
    }
}

async function loadConversation(conversationId) {
    const response = await fetch(`/api/history?conversation_id=${encodeURIComponent(conversationId)}`);
    const data = await response.json();
    if (!response.ok) {
        showToast(data.error || 'Không thể tải cuộc trò chuyện', 'error');
        return;
    }
    state.chatHistory = data.history || [];
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = '';
    state.chatHistory.forEach((entry) => {
        addMessageToChat(entry.question, 'user', entry.timestamp);
        addMessageToChat(entry.response, 'assistant', entry.timestamp);
    });
}

async function sendMessage() {
    const questionInput = document.getElementById('questionInput');
    const question = questionInput.value.trim();

    if (!question) {
        showToast('Vui lòng nhập câu hỏi', 'warning');
        return;
    }

    if (state.isLoading) return;

    state.isLoading = true;
    showLoading(true);
    document.getElementById('sendBtn').disabled = true;

    const chatMessages = document.getElementById('chatMessages');
    const welcome = chatMessages.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    addMessageToChat(question, 'user');
    questionInput.value = '';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, model: state.currentModel, top_k: 5 })
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'Lỗi khi gửi câu hỏi');
        }

        addMessageToChat(result.response, 'assistant', result.timestamp);
        state.lastCitations = result.citations || [];
        displayCitations(state.lastCitations);
        document.getElementById('citationsPanel').style.display = 'flex';
        state.chatHistory.push(result);
        showToast(`Tìm thấy ${result.num_retrieved || 0} tài liệu liên quan`, 'success');
    } catch (error) {
        console.error(error);
        addMessageToChat(`Lỗi: ${error.message}`, 'assistant');
        showToast(error.message, 'error');
    } finally {
        state.isLoading = false;
        showLoading(false);
        document.getElementById('sendBtn').disabled = false;
        questionInput.focus();
    }
}

function displayCitations(citations) {
    const citationsList = document.getElementById('citationsList');
    citationsList.innerHTML = '';

    if (!citations || !citations.length) {
        citationsList.innerHTML = '<div class="empty-state">Chưa có trích dẫn nào.</div>';
        return;
    }

    citations.forEach((citation, index) => {
        const item = document.createElement('div');
        item.className = 'citation-item';
        item.innerHTML = `
            <div class="citation-row">
                <span class="citation-id">${index + 1}</span>
                <div class="citation-content">
                    <div class="citation-title">${citation.section_title || 'Tài liệu liên quan'}</div>
                    <div class="citation-source"><strong>Nguồn:</strong> ${citation.source_label || citation.doc_id || 'Không rõ'}</div>
                    <div class="citation-score">📊 Độ tương tự: ${(Number(citation.similarity_score || 0) * 100).toFixed(1)}%</div>
                    <div class="citation-preview">${citation.content_preview || ''}</div>
                    ${citation.source_url && citation.source_url !== '#' ? `<a class="citation-link" href="${citation.source_url}" target="_blank" rel="noreferrer">Xem chi tiết</a>` : ''}
                </div>
            </div>
        `;
        citationsList.appendChild(item);
    });
}

function addMessageToChat(message, role, timestamp = null) {
    const chatMessages = document.getElementById('chatMessages');
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = message;
    messageEl.appendChild(content);

    if (timestamp) {
        const meta = document.createElement('div');
        meta.className = 'message-meta';
        meta.textContent = new Date(timestamp).toLocaleTimeString('vi-VN');
        messageEl.appendChild(meta);
    }

    chatMessages.appendChild(messageEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function newConversation() {
    try {
        const response = await fetch('/api/conversations/new', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Không thể tạo cuộc trò chuyện mới');
        state.chatHistory = [];
        renderWelcomeMessage();
        document.getElementById('citationsList').innerHTML = '';
        document.getElementById('citationsPanel').style.display = 'none';
        await loadConversationList();
        showToast('Đã tạo cuộc trò chuyện mới', 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function exportChat() {
    try {
        const response = await fetch('/api/export', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Không thể export');

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'chat-export.json';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showToast('Đã xuất lịch sử chat thành công', 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function loadPersonalDocs() {
    try {
        const response = await fetch('/api/personal-docs');
        const data = await response.json();
        state.personalDocs = data.documents || [];
        renderPersonalDocs();
    } catch (error) {
        console.error(error);
    }
}

function getUploadStatusLabel(doc) {
    if (doc && doc.status === 'uploaded') return 'Đã tải lên';
    if (doc && doc.status === 'success') return 'Đã xử lý';
    if (doc && doc.status === 'processing') return 'Đang xử lý';
    return doc && doc.status ? doc.status : 'Đã tải lên';
}

function renderPersonalDocs() {
    const list = document.getElementById('personalDocsList');
    list.innerHTML = '';

    if (!state.personalDocs.length) {
        list.innerHTML = '<div class="empty-state">Chưa có tài liệu cá nhân nào.</div>';
        return;
    }

    state.personalDocs.forEach((doc) => {
        const item = document.createElement('div');
        item.className = 'doc-item';
        item.innerHTML = `
            <div class="doc-info">
                <div class="doc-name">${doc.file_name}</div>
                <div class="doc-meta">${formatFileSize(doc.size || 0)} • ${formatDate(doc.uploaded_at)} • ${getUploadStatusLabel(doc)}</div>
            </div>
            <button class="btn btn-danger btn-sm" data-file="${doc.file_name}">Xóa</button>
        `;
        item.querySelector('button').addEventListener('click', () => deletePersonalDoc(doc.file_name));
        list.appendChild(item);
    });
}

async function uploadPersonalDocument() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        showLoading(true);
        const response = await fetch('/api/personal-docs/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Upload thất bại');

        state.personalDocs = data.documents || [];
        renderPersonalDocs();
        fileInput.value = '';
        showToast(`Tải lên thành công: ${data.file_name || file.name}`, 'success');
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function deletePersonalDoc(filename) {
    try {
        const response = await fetch(`/api/personal-docs/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Không thể xóa');
        state.personalDocs = data.documents || [];
        renderPersonalDocs();
        showToast('Tài liệu đã được xóa', 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function loadAdminDashboard() {
    const search =
        document.getElementById('adminSearch').value.trim();

    const category =
        document.getElementById('adminCategoryFilter').value;

    const type =
        document.getElementById('adminTypeFilter').value;

    try {
        const params = new URLSearchParams();

        if (search) {
            params.append('search', search);
        }

        if (category) {
            params.append('category', category);
        }

        if (type) {
            params.append('type', type);
        }

        const response = await fetch(
            `/api/admin/documents?${params.toString()}`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || 'Không thể tải danh sách tài liệu'
            );
        }

        state.adminDocuments = data.documents || [];

        // Cập nhật danh sách lĩnh vực
        renderAdminCategoryFilter();

        // Cập nhật gợi ý mã văn bản
        renderAdminDocumentSuggestions();

        renderAdminTable();
        renderAdminSummary();

    } catch (error) {
        console.error(
            'Lỗi loadAdminDashboard:',
            error
        );
    }
}
function renderAdminCategoryFilter() {
    const select =
        document.getElementById('adminCategoryFilter');

    if (!select) return;

    const currentValue = select.value;

    const categories = [
        ...new Set(
            state.adminDocuments
                .map(doc => doc.category)
                .filter(category =>
                    category &&
                    String(category).trim()
                )
        )
    ].sort();

    select.innerHTML = `
        <option value="">Tất cả lĩnh vực</option>

        ${categories.map(category => `
            <option value="${category}">
                ${category}
            </option>
        `).join('')}
    `;

    // Giữ lại lựa chọn hiện tại nếu vẫn tồn tại
    if (categories.includes(currentValue)) {
        select.value = currentValue;
    }
}
function renderAdminDocumentSuggestions() {
    const datalist =
        document.getElementById(
            'adminDocumentSuggestions'
        );

    if (!datalist) return;

    const documentNumbers = [
        ...new Set(
            state.adminDocuments
                .map(doc => doc.document_number)
                .filter(number =>
                    number &&
                    String(number).trim()
                )
        )
    ];

    datalist.innerHTML = documentNumbers
        .map(number => `
            <option value="${number}">
        `)
        .join('');
}
function renderAdminSummary() {
    const summary = document.getElementById('adminSummaryCards');

    const total =
        state.adminSummary.document_count ??
        state.adminDocuments.length;

    const categoryCount =
        state.adminSummary.category_count ??
        new Set(
            state.adminDocuments
                .map(doc => doc.category)
                .filter(Boolean)
        ).size;

    const todayUploads =
        state.adminSummary.today_upload_count ??
        state.adminDocuments.filter((doc) => {
            if (!doc.uploaded_at) return false;

            const uploadDate = new Date(doc.uploaded_at);
            const today = new Date();

            return uploadDate.toDateString() === today.toDateString();
        }).length;

    summary.innerHTML = `
        <div class="summary-card summary-blue">
            <span class="summary-label">Tổng tài liệu</span>
            <strong>${total}</strong>
        </div>

        <div class="summary-card summary-green">
            <span class="summary-label">Lĩnh vực</span>
            <strong>${categoryCount}</strong>
        </div>

        <div class="summary-card summary-red">
            <span class="summary-label">Tải lên hôm nay</span>
            <strong>${todayUploads}</strong>
        </div>
    `;
}

function renderAdminTable() {
    const tableBody = document.getElementById('adminTableBody');
    tableBody.innerHTML = '';

    if (!state.adminDocuments.length) {
        tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">Không tìm thấy tài liệu nào.</td></tr>';
        return;
    }

    state.adminDocuments.forEach((doc) => {
        const row = document.createElement('tr');
        const isActive = doc.is_active === true;
        const statusLabel = isActive ? 'Còn hiệu lực' : 'Hết hiệu lực';

        row.innerHTML = `
            <td>
                <div class="doc-file-name">${doc.file_name || doc.doc_id || 'Unknown'}</div>
            </td>
            <td>${doc.document_number || '—'}</td>
            <td>${doc.document_type || '—'}</td>
            <td>${formatDate(doc.created_at)}</td>
            <td>${formatFileSize(doc.size || 0)}</td>
            <td><span class="status-badge ${isActive ? 'active' : 'inactive'}">${statusLabel}</span></td>
            <td>
                <div class="table-actions">
                    <button class="small-btn toggle-btn" data-doc-id="${doc.doc_id}" data-active="${isActive}">
                        ${isActive ? 'Vô hiệu hóa' : 'Kích hoạt'}
                    </button>
                    <button class="small-btn delete-btn" data-doc-id="${doc.doc_id}">
                        Xóa
                    </button>
                </div>
            </td>
        `;

        const toggleButton = row.querySelector('.toggle-btn');
        toggleButton.addEventListener('click', () => updateDocumentStatus(doc.doc_id, !isActive));

        const deleteButton = row.querySelector('.delete-btn');
        deleteButton.addEventListener('click', () => deleteAdminDocument(doc.doc_id));

        tableBody.appendChild(row);
    });
}

async function updateDocumentStatus(docId, isActive) {
    try {
        const response = await fetch(`/api/admin/documents/${docId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Cập nhật trạng thái thất bại');
        showToast(isActive ? 'Đã kích hoạt tài liệu' : 'Đã vô hiệu hóa tài liệu', 'success');
        await fetchAdminSummary();
        await loadAdminDashboard();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function deleteAdminDocument(docId) {
    const confirmed = window.confirm('Bạn có chắc muốn xóa tài liệu này khỏi kho dữ liệu?');
    if (!confirmed) return;

    try {
        const response = await fetch(`/api/admin/documents/${docId}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Xóa tài liệu thất bại');
        showToast('Tài liệu đã được xóa', 'success');
        await fetchAdminSummary();
        await loadAdminDashboard();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function fetchAdminSummary() {
    try {
        const response = await fetch('/api/admin/dashboard');
        const data = await response.json();
        state.adminSummary = data.summary || state.adminSummary;
    } catch (error) {
        console.error(error);
    }
}

function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString('vi-VN');
}

function formatFileSize(bytes) {
    if (!bytes) return '0 KB';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }
    return `${size.toFixed(1)} ${units[unitIndex]}`;
}

function showLoading(show) {
    const indicator = document.getElementById('loadingIndicator');
    indicator.style.display = show ? 'flex' : 'none';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

document.addEventListener('DOMContentLoaded', async () => {
    setupPageState();
    setupEventListeners();
    await loadModels();
    await loadChatHistory();
    await loadConversationList();
    await loadPersonalDocs();
    await fetchAdminSummary();
    await loadAdminDashboard();
    document.getElementById('citationsPanel').style.display = 'none';
});
