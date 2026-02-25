/**
 * UI Components & Utilities
 */
window.ui = {
    modal: {
        overlay: null,
        title: null,
        body: null,
        cancelBtn: null,
        confirmBtn: null,
        closeBtn: null,
        onConfirm: null
    },

    init() {
        // Create modal DOM if not exists (or simpler: just bind to existing)
        // We assume DOM is present in base.html
        this.modal.overlay = document.getElementById('modal-overlay');
        this.modal.title = document.getElementById('modal-title');
        this.modal.body = document.getElementById('modal-body');
        this.modal.cancelBtn = document.getElementById('modal-cancel');
        this.modal.confirmBtn = document.getElementById('modal-confirm');
        this.modal.closeBtn = document.getElementById('modal-close');

        // Bind events
        if (this.modal.cancelBtn) {
            this.modal.cancelBtn.addEventListener('click', () => this.closeModal());
        }
        if (this.modal.closeBtn) {
            this.modal.closeBtn.addEventListener('click', () => this.closeModal());
        }
        if (this.modal.confirmBtn) {
            this.modal.confirmBtn.addEventListener('click', () => {
                if (this.modal.onConfirm) {
                    this.modal.onConfirm();
                }
                this.closeModal();
            });
        }
        
        // Close on clicking overlay
        if (this.modal.overlay) {
            this.modal.overlay.addEventListener('click', (e) => {
                if (e.target === this.modal.overlay) {
                    this.closeModal();
                }
            });
        }
    },

    /**
     * Show confirmation modal
     * @param {string} message - Message to display
     * @param {function} onConfirm - Callback when confirmed
     * @param {string} title - Optional title
     */
    confirm(message, onConfirm, title = null) {
        if (!this.modal.overlay) this.init();
        
        this.modal.title.textContent = title || t('action.confirm');
        this.modal.body.textContent = message;
        this.modal.onConfirm = onConfirm;
        
        this.modal.confirmBtn.style.display = 'inline-flex';
        this.modal.cancelBtn.style.display = 'inline-flex';
        
        this.openModal();
    },

    /**
     * Show alert modal
     * @param {string} message - Message body
     * @param {string} title - Title
     */
    alert(message, title = null) {
        if (!this.modal.overlay) this.init();

        this.modal.title.textContent = title || 'Alert';
        this.modal.body.textContent = message;
        this.modal.onConfirm = null;
        
        this.modal.confirmBtn.style.display = 'inline-flex';
        this.modal.cancelBtn.style.display = 'none';

        this.openModal();
    },

    openModal() {
        this.modal.overlay.classList.add('open');
    },

    closeModal() {
        this.modal.overlay.classList.remove('open');
        this.modal.onConfirm = null;
    }
};

// Auto init on load
document.addEventListener('DOMContentLoaded', () => {
    ui.init();
});
