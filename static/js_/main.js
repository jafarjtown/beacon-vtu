/**
 * PayPlus VTU App - Main JavaScript
 * Mobile-first interactive logic for Django app
 */

(function() {
    'use strict';

    // ===== APP NAMESPACE =====
    window.app = {};

    // ===== STATE =====
    const state = {
        balance: 0.00,
        totalWatched: 0,
        totalEarned: 0.00,
        adsToday: 0,
        adsLimit: 15,
        tasks: {
            join: { current: 0, limit: 4, reward: 0.05 },
            bots: { current: 0, limit: 10, reward: 0.05 },
            subscribe: { current: 0, limit: 1, reward: 0.05 }
        },
        friendsInvited: 0,
        earnedFromInvites: 0.00,
        currentTab: 'ads',
        selectedMethod: 'usdt',
        language: 'en',
        isWatchingAd: false,
        confirmCallback: null,
        userId: '7861163240',
        username: 'Jafaru'
    };

    // ===== CSRF TOKEN (Django) =====
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrfToken = getCookie('csrftoken');

    // ===== API HELPER =====
    async function api(endpoint, options = {}) {
        const url = endpoint.startsWith('/') ? endpoint : `/api/${endpoint}/`;
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        };
        
        showLoading();
        try {
            const response = await fetch(url, { ...defaults, ...options });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || 'Request failed');
            return data;
        } catch (error) {
            showToast(error.message, 'error');
            throw error;
        } finally {
            hideLoading();
        }
    }

    // ===== LOCAL STORAGE =====
    function loadData() {
        try {
            const saved = localStorage.getItem('payplus_data');
            if (saved) {
                const data = JSON.parse(saved);
                Object.assign(state, data);
            }
        } catch (e) {
            console.warn('Failed to load saved data:', e);
        }
    }

    function saveData() {
        try {
            localStorage.setItem('payplus_data', JSON.stringify({
                balance: state.balance,
                totalWatched: state.totalWatched,
                totalEarned: state.totalEarned,
                adsToday: state.adsToday,
                tasks: state.tasks,
                friendsInvited: state.friendsInvited,
                earnedFromInvites: state.earnedFromInvites,
                language: state.language
            }));
        } catch (e) {
            console.warn('Failed to save data:', e);
        }
    }

    // ===== TOAST NOTIFICATIONS =====
    function showToast(message, type = 'success', duration = 3000) {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-times-circle',
            warning: 'fa-exclamation-circle',
            info: 'fa-info-circle'
        };

        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;
        toast.innerHTML = `
            <i class="fas ${icons[type] || icons.info} toast__icon"></i>
            <span>${escapeHtml(message)}</span>
            <button class="toast__close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;

        container.appendChild(toast);

        // Auto remove
        setTimeout(() => {
            toast.style.animation = 'toastFadeOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // ===== LOADING OVERLAY =====
    function showLoading(text = 'Loading...') {
        const overlay = document.getElementById('loadingOverlay');
        const textEl = document.getElementById('loadingText');
        if (overlay) {
            overlay.classList.add('active');
            if (textEl) textEl.textContent = text;
        }
    }

    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.classList.remove('active');
    }

    // ===== MODAL SYSTEM =====
    function openModal(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.add('modal-overlay--active');
            document.body.style.overflow = 'hidden';
        }
    }

    function closeModal(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.remove('modal-overlay--active');
            document.body.style.overflow = '';
        }
    }

    // Close modal on backdrop click
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal-overlay')) {
            e.target.classList.remove('modal-overlay--active');
            document.body.style.overflow = '';
        }
    });

    // Close modal on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay--active').forEach(modal => {
                modal.classList.remove('modal-overlay--active');
            });
            document.body.style.overflow = '';
        }
    });

    // ===== CONFIRM DIALOG =====
    function showConfirm(options) {
        const {
            title = 'Confirm',
            message = 'Are you sure?',
            type = 'info',
            confirmText = 'OK',
            cancelText = 'Cancel',
            onConfirm = () => {},
            onCancel = () => {}
        } = options;

        const icons = {
            success: { icon: 'fa-check-circle', class: 'dialog__icon--success' },
            error: { icon: 'fa-times-circle', class: 'dialog__icon--error' },
            warning: { icon: 'fa-exclamation-triangle', class: 'dialog__icon--warning' },
            info: { icon: 'fa-info-circle', class: 'dialog__icon--info' }
        };

        const iconConfig = icons[type] || icons.info;

        document.getElementById('confirmIcon').className = `dialog__icon ${iconConfig.class}`;
        document.getElementById('confirmIcon').innerHTML = `<i class="fas ${iconConfig.icon}"></i>`;
        document.getElementById('confirmTitle').textContent = title;
        document.getElementById('confirmMessage').textContent = message;
        document.getElementById('confirmAction').textContent = confirmText;
        document.getElementById('confirmCancel').textContent = cancelText;

        state.confirmCallback = () => {
            onConfirm();
            closeModal('confirmModal');
        };

        document.getElementById('confirmCancel').onclick = () => {
            onCancel();
            closeModal('confirmModal');
        };

        openModal('confirmModal');
    }

    // ===== TAB SWITCHING =====
    function switchTab(tabName) {
        // Hide all pages
        document.querySelectorAll('.page').forEach(page => {
            page.classList.remove('active');
        });

        // Show selected page
        const targetPage = document.getElementById(`page-${tabName}`);
        if (targetPage) {
            targetPage.classList.add('active');
        }

        // Update nav items
        document.querySelectorAll('.bottom-nav__item').forEach(item => {
            item.classList.remove('bottom-nav__item--active');
            if (item.dataset.tab === tabName) {
                item.classList.add('bottom-nav__item--active');
            }
        });

        state.currentTab = tabName;
        saveData();

        // Update URL without reload (optional)
        history.replaceState(null, null, `#${tabName}`);
    }

    // ===== AD WATCHING =====
    function watchAd() {
        if (state.isWatchingAd) return;
        if (state.adsToday >= state.adsLimit) {
            showToast('Daily ad limit reached. Come back tomorrow!', 'warning');
            return;
        }

        state.isWatchingAd = true;
        const overlay = document.getElementById('adOverlay');
        const timerEl = document.getElementById('adTimer');
        let timeLeft = 15;

        overlay.classList.add('active');
        timerEl.textContent = timeLeft;

        const timer = setInterval(() => {
            timeLeft--;
            timerEl.textContent = timeLeft;

            if (timeLeft <= 0) {
                clearInterval(timer);
                completeAd();
            }
        }, 1000);

        // Allow skip after 5 seconds (optional)
        setTimeout(() => {
            overlay.addEventListener('click', function skipHandler() {
                clearInterval(timer);
                completeAd();
                overlay.removeEventListener('click', skipHandler);
            }, { once: true });
        }, 5000);
    }

    function completeAd() {
        const overlay = document.getElementById('adOverlay');
        overlay.classList.remove('active');
        state.isWatchingAd = false;

        const reward = 0.20;
        state.balance += reward;
        state.totalEarned += reward;
        state.totalWatched++;
        state.adsToday++;

        saveData();
        updateUI();
        showToast(`+$${reward.toFixed(2)} earned!`, 'success');

        // Sync with server
        syncBalance();
    }

    // ===== TASKS =====
    function doTask(taskType) {
        const task = state.tasks[taskType];
        if (!task) return;

        if (task.current >= task.limit) {
            showToast('Task already completed!', 'info');
            return;
        }

        // Simulate task completion
        showLoading('Processing...');
        setTimeout(() => {
            hideLoading();
            task.current++;
            state.balance += task.reward;
            saveData();
            updateUI();
            showToast(`+$${task.reward.toFixed(2)} earned!`, 'success');
            syncBalance();
        }, 1500);
    }

    // ===== INVITE SYSTEM =====
    function copyLink() {
        const link = document.getElementById('inviteLink');
        if (!link) return;

        const url = link.textContent.trim();
        navigator.clipboard.writeText(url).then(() => {
            const btn = document.getElementById('copyBtn');
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i><span>Copied!</span>';
            btn.classList.add('copied');
            showToast('Invite link copied to clipboard!', 'success');

            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.classList.remove('copied');
            }, 2000);
        }).catch(() => {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = url;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            showToast('Invite link copied!', 'success');
        });
    }

    function shareLink() {
        const url = document.getElementById('inviteLink')?.textContent.trim();
        const text = `Join PayPlus and earn money! Use my invite link: ${url}`;

        if (navigator.share) {
            navigator.share({
                title: 'PayPlus - Earn Money',
                text: text,
                url: url
            }).catch(() => {
                // User cancelled
            });
        } else {
            copyLink();
        }
    }

    // ===== WITHDRAWAL =====
    function selectMethod(method) {
        state.selectedMethod = method;

        document.querySelectorAll('.payment-method').forEach(el => {
            el.classList.remove('payment-method--active');
            if (el.dataset.method === method) {
                el.classList.add('payment-method--active');
            }
        });

        // Update wallet placeholder
        const walletInput = document.getElementById('walletAddress');
        const hints = {
            usdt: 'Enter your USDT TRC20 wallet address',
            paypal: 'Enter your PayPal email address',
            topup: 'Enter your mobile number'
        };
        if (walletInput) {
            walletInput.placeholder = hints[method] || 'Enter details...';
        }
    }

    function submitWithdrawal() {
        const amount = parseFloat(document.getElementById('withdrawAmount')?.value);
        const wallet = document.getElementById('walletAddress')?.value.trim();

        if (!amount || amount < 10) {
            showToast('Minimum withdrawal is $10.00', 'error');
            return;
        }

        if (amount > state.balance) {
            showToast('Insufficient balance', 'error');
            return;
        }

        if (!wallet) {
            showToast('Please enter wallet address', 'error');
            return;
        }

        showConfirm({
            title: 'Confirm Withdrawal',
            message: `Withdraw $${amount.toFixed(2)} to your ${state.selectedMethod.toUpperCase()} wallet?`,
            type: 'warning',
            confirmText: 'Confirm',
            onConfirm: () => {
                showLoading('Processing withdrawal...');
                
                // API call
                api('withdraw', {
                    method: 'POST',
                    body: JSON.stringify({
                        amount: amount,
                        method: state.selectedMethod,
                        wallet_address: wallet
                    })
                }).then(data => {
                    hideLoading();
                    state.balance -= amount;
                    saveData();
                    updateUI();
                    showToast('Withdrawal request submitted!', 'success');
                    document.getElementById('withdrawAmount').value = '';
                    document.getElementById('walletAddress').value = '';
                }).catch(() => {
                    hideLoading();
                });
            }
        });
    }

    // ===== LANGUAGE =====
    function setLanguage(lang) {
        state.language = lang;
        saveData();

        document.querySelectorAll('.lang-option').forEach(el => {
            el.classList.remove('active');
        });
        event.currentTarget.classList.add('active');

        const langNames = { en: 'English', ha: 'Hausa', yo: 'Yoruba', ig: 'Igbo' };
        showToast(`Language changed to ${langNames[lang] || lang}`, 'success');

        // Close modal after short delay
        setTimeout(() => closeModal('langModal'), 500);

        // In production, reload page or fetch translations
        // window.location.reload();
    }

    // ===== SUPPORT =====
    function showSupport() {
        openModal('supportModal');
    }

    function showLanguage() {
        openModal('langModal');
    }

    function openChat() {
        window.open('https://t.me/PayPlusSupport', '_blank');
    }

    function sendEmail() {
        window.location.href = 'mailto:support@payplus.com';
    }

    function openFAQ() {
        window.location.href = '/faq/';
    }

    // ===== NAVIGATION =====
    function goBack() {
        if (window.history.length > 1) {
            window.history.back();
        } else {
            switchTab('ads');
        }
    }

    function toggleDropdown() {
        showToast('Dropdown menu coming soon', 'info');
    }

    function showMenu() {
        showToast('Menu coming soon', 'info');
    }

    // ===== UI UPDATES =====
    function updateUI() {
        // Balance
        const balanceEl = document.getElementById('totalBalance');
        if (balanceEl) balanceEl.textContent = `$${state.balance.toFixed(2)}`;

        // Stats
        const watchedEl = document.getElementById('totalWatched');
        if (watchedEl) watchedEl.textContent = state.totalWatched;

        const earnedEl = document.getElementById('totalEarned');
        if (earnedEl) earnedEl.textContent = `$${state.totalEarned.toFixed(2)}`;

        const availEl = document.getElementById('availBalance');
        if (availEl) availEl.textContent = `$${state.balance.toFixed(2)}`;

        // Ad progress
        const adCountEl = document.getElementById('adCount');
        if (adCountEl) adCountEl.textContent = `${state.adsToday} / ${state.adsLimit} today`;

        const adProgressBar = document.getElementById('adProgressBar');
        if (adProgressBar) {
            adProgressBar.style.width = `${(state.adsToday / state.adsLimit) * 100}%`;
        }

        // Tasks
        updateTaskUI('join', 'taskJoinCount', 'taskJoinBar');
        updateTaskUI('bots', 'taskBotsCount', 'taskBotsBar');
        updateTaskUI('subscribe', 'taskSubCount', 'taskSubBar');

        // Invite stats
        const friendsEl = document.getElementById('friendsInvited');
        if (friendsEl) friendsEl.textContent = state.friendsInvited;

        const inviteEarnedEl = document.getElementById('earnedFromInvites');
        if (inviteEarnedEl) inviteEarnedEl.textContent = `$${state.earnedFromInvites.toFixed(2)}`;
    }

    function updateTaskUI(taskType, countId, barId) {
        const task = state.tasks[taskType];
        if (!task) return;

        const countEl = document.getElementById(countId);
        if (countEl) countEl.textContent = `${task.current} / ${task.limit}`;

        const barEl = document.getElementById(barId);
        if (barEl) barEl.style.width = `${(task.current / task.limit) * 100}%`;
    }

    // ===== SERVER SYNC =====
    function syncBalance() {
        // Debounced sync to server
        clearTimeout(window._syncTimeout);
        window._syncTimeout = setTimeout(() => {
            api('sync', {
                method: 'POST',
                body: JSON.stringify({
                    balance: state.balance,
                    total_earned: state.totalEarned,
                    ads_watched: state.totalWatched
                })
            }).catch(() => {
                // Will retry on next action
            });
        }, 2000);
    }

    // ===== UTILITY =====
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatNumber(num) {
        return new Intl.NumberFormat('en-US').format(num);
    }

    function formatCurrency(amount) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(amount);
    }

    // ===== RIPPLE EFFECT =====
    function initRipple() {
        document.querySelectorAll('.ripple').forEach(btn => {
            btn.addEventListener('click', function(e) {
                const rect = this.getBoundingClientRect();
                const ripple = document.createElement('span');
                const size = Math.max(rect.width, rect.height);
                const x = e.clientX - rect.left - size / 2;
                const y = e.clientY - rect.top - size / 2;

                ripple.style.cssText = `
                    position: absolute;
                    border-radius: 50%;
                    background: rgba(255,255,255,0.3);
                    width: ${size}px;
                    height: ${size}px;
                    left: ${x}px;
                    top: ${y}px;
                    pointer-events: none;
                    animation: rippleEffect 0.6s ease-out;
                `;

                this.style.position = 'relative';
                this.style.overflow = 'hidden';
                this.appendChild(ripple);

                setTimeout(() => ripple.remove(), 600);
            });
        });
    }

    // Add ripple animation
    const rippleStyle = document.createElement('style');
    rippleStyle.textContent = `
        @keyframes rippleEffect {
            from { transform: scale(0); opacity: 1; }
            to { transform: scale(2); opacity: 0; }
        }
    `;
    document.head.appendChild(rippleStyle);

    // ===== PULL TO REFRESH =====
    function initPullToRefresh() {
        let startY = 0;
        let isPulling = false;
        const container = document.querySelector('.app-container');

        container?.addEventListener('touchstart', e => {
            if (container.scrollTop === 0) {
                startY = e.touches[0].clientY;
                isPulling = true;
            }
        }, { passive: true });

        container?.addEventListener('touchmove', e => {
            if (!isPulling) return;
            const diff = e.touches[0].clientY - startY;
            if (diff > 80) {
                isPulling = false;
                showLoading('Refreshing...');
                setTimeout(() => {
                    hideLoading();
                    showToast('Refreshed!', 'success');
                }, 1000);
            }
        }, { passive: true });
    }

    // ===== HAPTIC FEEDBACK =====
    function haptic(type = 'light') {
        if (navigator.vibrate) {
            const patterns = {
                light: [10],
                medium: [20],
                heavy: [30],
                success: [10, 50, 10],
                error: [30, 50, 30]
            };
            navigator.vibrate(patterns[type] || patterns.light);
        }
    }

    // ===== INITIALIZATION =====
    function init() {
        loadData();
        updateUI();
        initRipple();
        initPullToRefresh();

        // Handle URL hash for tab state
        const hash = window.location.hash.replace('#', '');
        if (hash && ['ads', 'tasks', 'invite', 'withdraw'].includes(hash)) {
            switchTab(hash);
        }

        // Update time
        setInterval(() => {
            const now = new Date();
            const hours = now.getHours();
            const minutes = now.getMinutes().toString().padStart(2, '0');
            const ampm = hours >= 12 ? 'PM' : 'AM';
            const displayHours = hours % 12 || 12;
            const el = document.getElementById('statusTime');
            if (el) el.textContent = `${displayHours}:${minutes} ${ampm}`;
        }, 60000);

        console.log('PayPlus App initialized');
    }

    // ===== EXPOSE PUBLIC API =====
    Object.assign(window.app, {
        // Navigation
        switchTab,
        goBack,
        toggleDropdown,
        showMenu,

        // Actions
        watchAd,
        doTask,
        copyLink,
        shareLink,
        selectMethod,
        submitWithdrawal,

        // Modals
        showSupport,
        showLanguage,
        setLanguage,
        openChat,
        sendEmail,
        openFAQ,
        openModal,
        closeModal,
        showConfirm,
        confirmAction: () => state.confirmCallback?.(),

        // Utilities
        showToast,
        showLoading,
        hideLoading,
        haptic,
        formatNumber,
        formatCurrency,

        // State (read-only access)
        getState: () => ({ ...state })
    });

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
