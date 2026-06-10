/*
═══════════════════════════════════════════════════════════════════════════════
HỆ THỐNG TRA CỨU TÀI LIỆU PHÁP LỤC - JAVASCRIPT APPLICATION
═══════════════════════════════════════════════════════════════════════════════

Chức năng:
✓ Gửi câu hỏi đến server
✓ Hiển thị kết quả retrieval
✓ Quản lý lịch sử chat
✓ Export dữ liệu
✓ UI interactions
*/

// ═════════════════════════════════════════════════════════════════════════════
// STATE MANAGEMENT
// ═════════════════════════════════════════════════════════════════════════════

const state = {
    isLoading: false,
    currentModel: null,
    models: [],
    lastCitations: [],
    chatHistory: []
};

// ═════════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═════════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Initializing Legal Document Chat UI...');
    
    // Load available models
    await loadModels();
    
    // Setup event listeners
    setupEventListeners();
    
    // Load chat history
    await loadChatHistory();
    
    console.log('✓ Initialization complete');
});

// ═════════════════════════════════════════════════════════════════════════════
// MODEL LOADING
// ═════════════════════════════════════════════════════════════════════════════

async function loadModels() {

    state.models = [
        "BAAI/bge-m3"
    ];

    state.currentModel = "BAAI/bge-m3";

    const select =
        document.getElementById(
            "modelSelect"
        );

    select.innerHTML = `
        <option value="BAAI/bge-m3">
            BAAI/bge-m3
        </option>
    `;
}

// ═════════════════════════════════════════════════════════════════════════════
// EVENT LISTENERS
// ═════════════════════════════════════════════════════════════════════════════

function setupEventListeners() {
    /**
     * Thiết lập các event listeners cho UI
     */
    
    // Model selection
    document.getElementById('modelSelect').addEventListener('change', (e) => {
        state.currentModel = e.target.value;
        console.log(`Model changed to: ${state.currentModel}`);
    });
    
    // Question input
    const questionInput = document.getElementById('questionInput');
    questionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !state.isLoading) {
            sendMessage();
        }
    });
    
    // Clear history button
    document.getElementById('clearHistoryBtn').addEventListener('click', clearHistory);
    
    // Export button
    document.getElementById('exportBtn').addEventListener('click', exportChat);
}

// ═════════════════════════════════════════════════════════════════════════════
// MESSAGE HANDLING
// ═════════════════════════════════════════════════════════════════════════════

async function sendMessage() {
    /**
     * ════════════════════════════════════════════════════════════════
     * Gửi câu hỏi đến server và xử lý phản hồi
     * 
     * Quy trình:
     * 1. Lấy câu hỏi từ input
     * 2. Hiển thị loading indicator
     * 3. Gửi request tới /api/chat
     * 4. Hiển thị kết quả
     * 5. Lưu vào lịch sử
     * ════════════════════════════════════════════════════════════════
     */
    
    const questionInput = document.getElementById('questionInput');
    const question = questionInput.value.trim();
    
    // Validation
    if (!question) {
        showToast('Vui lòng nhập câu hỏi', 'warning');
        return;
    }
    
    if (!state.currentModel) {
        showToast('Vui lòng chọn model', 'warning');
        return;
    }
    
    // Clear input
    questionInput.value = '';
    
    // Show loading
    state.isLoading = true;
    showLoading(true);
    document.getElementById('sendBtn').disabled = true;
    
    try {
        // Remove welcome message if first message
        const chatMessages = document.getElementById('chatMessages');
        const welcome = chatMessages.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
        }
        
        // Add user message to chat
        addMessageToChat(question, 'user');
        
        // Send request to server
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                model: state.currentModel,
                top_k: 5
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Server error');
        }
        
        const result = await response.json();
        
        // Add assistant message
        addMessageToChat(result.response, 'assistant', result.timestamp);
        
        // Store citations
        state.lastCitations = result.citations;
        
        // Update citations button
        const citationBtn = document.getElementById('showCitationsBtn');
        citationBtn.style.display = 'flex';
        document.getElementById('citationCount').textContent = result.num_retrieved;
        
        // Display citations panel
        displayCitations(result.citations);
        
        // Add to history
        state.chatHistory.push(result);
        
        console.log(`✓ Processed response with ${result.num_retrieved} citations`);
        showToast(`Tìm thấy ${result.num_retrieved} tài liệu liên quan`, 'success');
        
    } catch (error) {
        console.error('❌ Error:', error);
        showToast(`Lỗi: ${error.message}`, 'error');
        addMessageToChat(`Lỗi: ${error.message}`, 'assistant');
    } finally {
        state.isLoading = false;
        showLoading(false);
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('questionInput').focus();
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// CHAT UI
// ═════════════════════════════════════════════════════════════════════════════

function addMessageToChat(message, role, timestamp = null) {
    /**
     * Thêm một message vào chat display
     * 
     * Parameters:
     *   message: Nội dung message
     *   role: 'user' hoặc 'assistant'
     *   timestamp: Thời gian (optional)
     */
    
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
        const time = new Date(timestamp).toLocaleTimeString('vi-VN');
        meta.textContent = time;
        messageEl.appendChild(meta);
    }
    
    chatMessages.appendChild(messageEl);
    
    // Auto scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function displayCitations(citations) {
    /**
     * Hiển thị danh sách citations (tài liệu tham khảo)
     */
    
    const citationsList = document.getElementById('citationsList');
    citationsList.innerHTML = '';
    
    citations.forEach(citation => {
        const item = document.createElement('div');
        item.className = 'citation-item';
        
        item.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 0.5rem;">
                <span class="citation-id">${citation.id}</span>
                <div style="flex: 1;">
                    <div class="citation-title">${citation.section_title}</div>
                    <div class="citation-source">
                        <strong>Nguồn:</strong> ${citation.doc_id}
                    </div>
                    <div class="citation-score">
                        📊 Độ tương tự: ${(citation.similarity_score * 100).toFixed(1)}%
                    </div>
                    <div class="citation-preview">${citation.content_preview}</div>
                </div>
            </div>
        `;
        
        citationsList.appendChild(item);
    });
}

function toggleCitationsPanel() {
    /**
     * Bật/tắt citations panel
     */
    const panel = document.getElementById('citationsPanel');
    if (panel.style.display === 'none' || panel.style.display === '') {
        panel.style.display = 'flex';
    } else {
        panel.style.display = 'none';
    }
}

function closeCitationsPanel() {
    /**
     * Đóng citations panel
     */
    document.getElementById('citationsPanel').style.display = 'none';
}

// ═════════════════════════════════════════════════════════════════════════════
// CHAT HISTORY
// ═════════════════════════════════════════════════════════════════════════════

async function loadChatHistory() {
    /**
     * Tải lịch sử chat từ server
     */
    try {
        const response = await fetch('/history');
        const data = await response.json();
        state.chatHistory = data.history || [];
        console.log(`✓ Loaded ${state.chatHistory.length} messages from history`);
    } catch (error) {
        console.error('❌ Error loading history:', error);
    }
}

async function clearHistory() {
    /**
     * Xóa lịch sử chat
     */
    if (confirm('Bạn chắc chắn muốn xóa toàn bộ lịch sử chat?')) {
        try {
            const response = await fetch('/api/clear-history', {
                method: 'POST'
            });
            
            if (response.ok) {
                state.chatHistory = [];
                document.getElementById('chatMessages').innerHTML = `
                    <div class="welcome-message">
                        <h2>👋 Chào mừng đến với Hệ Thống Tra Cứu Tài Liệu Pháp Luật</h2>
                        <p>Đặt câu hỏi về pháp luật và nhận câu trả lời dựa trên cơ sở dữ liệu pháp lý</p>
                        <div class="feature-grid">
                            <div class="feature">
                                <i class="fas fa-search"></i>
                                <span>Tìm kiếm vector</span>
                            </div>
                            <div class="feature">
                                <i class="fas fa-quote-left"></i>
                                <span>Trích dẫn chính xác</span>
                            </div>
                            <div class="feature">
                                <i class="fas fa-robot"></i>
                                <span>Trả lời bằng LLM</span>
                            </div>
                            <div class="feature">
                                <i class="fas fa-link"></i>
                                <span>Liên kết tài liệu</span>
                            </div>
                        </div>
                    </div>
                `;
                document.getElementById('citationsPanel').style.display = 'none';
                showToast('Lịch sử đã được xóa', 'success');
            }
        } catch (error) {
            console.error('❌ Error clearing history:', error);
            showToast('Lỗi xóa lịch sử', 'error');
        }
    }
}

async function exportChat() {
    /**
     * Export lịch sử chat thành JSON
     */
    try {
        const response = await fetch('/export');
        const data = await response.json();
        
        // Create downloadable file
        const dataStr = JSON.stringify(data, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `chat-export-${new Date().getTime()}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        
        showToast('Đã export lịch sử chat thành công', 'success');
        console.log('✓ Chat exported');
        
    } catch (error) {
        console.error('❌ Error exporting:', error);
        showToast('Lỗi export', 'error');
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// UI UTILITIES
// ═════════════════════════════════════════════════════════════════════════════

function showLoading(show) {
    /**
     * Hiển thị/ẩn loading indicator
     */
    const indicator = document.getElementById('loadingIndicator');
    indicator.style.display = show ? 'flex' : 'none';
}

function showToast(message, type = 'info') {
    /**
     * Hiển thị notification toast
     * 
     * Types: 'success', 'error', 'warning', 'info'
     */
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    
    toast.innerHTML = `
        <span style="font-size: 1.2rem;">${icons[type]}</span>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Auto remove after 4 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ═════════════════════════════════════════════════════════════════════════════
// DEBUGGING
// ═════════════════════════════════════════════════════════════════════════════

console.log(`
╔════════════════════════════════════════════════════════════════════╗
║            LEGAL DOCUMENT CHAT UI - INITIALIZED                   ║
║                                                                    ║
║  📍 API Endpoint: /api/chat                                       ║
║  📊 Models: Loaded dynamically                                    ║
║  💾 Storage: Session-based                                        ║
║  🎯 Version: 1.0.0                                                ║
╚════════════════════════════════════════════════════════════════════╝
`);
