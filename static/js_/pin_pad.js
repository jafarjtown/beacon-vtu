/**
 * Transaction-PIN keypad. Entirely button-driven — there is no text input
 * involved in entry, so nothing here ever summons a mobile on-screen
 * keyboard. The digits are held in memory and only written into a hidden
 * form field at the moment of submit.
 *
 * Wire-up per page: give the button that should open this modal the class
 * "js-pin-trigger". See templates/partials/pin_pad.html for full usage.
 */
(function () {
  const DEFAULT_PIN_LENGTH = 4;

  const overlay = document.getElementById('pinModalOverlay');
  if (!overlay) return; // partial not included on this page — no-op

  const boxesWrap = document.getElementById('pinDots');
  const errorEl = document.getElementById('pinError');
  const subEl = document.getElementById('pinModalSub');
  const cancelBtn = document.getElementById('pinModalCancel');
  const backspaceBtn = document.getElementById('pinBackspace');
  const entryPanel = document.getElementById('pinEntryPanel');
  const processingPanel = document.getElementById('pinProcessingPanel');
  const processingText = document.getElementById('pinProcessingText');
  const footer = document.getElementById('pinModalFooter');
  const defaultSubText = subEl.textContent;
  const defaultProcessingText = processingText.textContent;

  let currentPin = '';
  let pinLength = DEFAULT_PIN_LENGTH;
  let activeForm = null;
  let activeTrigger = null;

  function buildBoxes(length) {
    boxesWrap.innerHTML = '';
    for (let i = 0; i < length; i++) {
      const box = document.createElement('span');
      box.className = 'pin-box';
      boxesWrap.appendChild(box);
    }
  }

  function renderBoxes() {
    boxesWrap.querySelectorAll('.pin-box').forEach((box, i) => {
      box.classList.toggle('filled', i < currentPin.length);
    });
  }

  function resetEntry() {
    currentPin = '';
    errorEl.hidden = true;
    renderBoxes();
  }

  function showEntryPanel() {
    processingPanel.hidden = true;
    entryPanel.hidden = false;
    footer.hidden = false;
  }

  function showProcessingPanel(trigger) {
    processingText.textContent = (trigger && trigger.dataset.pinProcessingText) || defaultProcessingText;
    entryPanel.hidden = true;
    footer.hidden = true;
    processingPanel.hidden = false;
  }

  function openModal(trigger) {
    activeForm = trigger.closest('form');
    if (!activeForm) return;

    activeTrigger = trigger;
    pinLength = parseInt(trigger.dataset.pinLength || DEFAULT_PIN_LENGTH, 10);
    subEl.textContent = trigger.dataset.pinPrompt || defaultSubText;

    // Always reopen on the entry panel — a modal reopened after a
    // previous PIN error (or, in principle, any other re-render) should
    // never come back still showing the processing spinner from before.
    showEntryPanel();

    buildBoxes(pinLength);
    resetEntry();

    overlay.classList.add('open');
    document.body.classList.add('pin-modal-locked');
  }

  function closeModal() {
    // Once the PIN is complete and we're waiting on the actual page
    // navigation, there's nothing left to "cancel" — the form is already
    // submitting (or about to). Letting Escape/overlay-click/Cancel close
    // the modal here would just look like the purchase silently vanished.
    if (!processingPanel.hidden) return;

    overlay.classList.remove('open');
    document.body.classList.remove('pin-modal-locked');
    activeForm = null;
    activeTrigger = null;
  }

  function showError(message) {
    boxesWrap.classList.add('shake');
    setTimeout(() => boxesWrap.classList.remove('shake'), 400);
    currentPin = '';
    renderBoxes();
    errorEl.textContent = message || 'Incorrect PIN. Try again.';
    errorEl.hidden = false;
  }
  async function _verify_pin(pin) {
    
    const res = await fetch(
        "/accounts/verify-pin/?pin=" + encodeURIComponent(pin)
    );

    const data = await res.json();

    return {
        success: data.success,
        message: data.message
    };
  }
  
  async function submitPin() {
    if (!activeForm) return;
    // verify pin
    const result = await _verify_pin(currentPin);
    
    if (!result.success) {
      showError(result.message);
      return
    }
    let hiddenInput = activeForm.querySelector('input[name="pin"]');
    if (!hiddenInput) {
      hiddenInput = document.createElement('input');
      hiddenInput.type = 'hidden';
      hiddenInput.name = 'pin';
      activeForm.appendChild(hiddenInput);
    }
    hiddenInput.value = currentPin;

    // Brief pause so the last box is visibly filled before swapping to
    // the processing view — otherwise the fill feels clipped. The
    // processing view itself then stays up for however long the actual
    // page load takes (network + server processing), not a fixed delay.
    setTimeout(() => {
      showProcessingPanel(activeTrigger);
      activeForm.submit();
    }, 150);
  }

  function pressDigit(digit) {
    if (currentPin.length >= pinLength) return;
    currentPin += digit;
    renderBoxes();
    if (currentPin.length === pinLength) submitPin();
  }

  function pressBackspace() {
    currentPin = currentPin.slice(0, -1);
    errorEl.hidden = true;
    renderBoxes();
  }

  document.querySelectorAll('.js-pin-trigger').forEach((trigger) => {
    trigger.addEventListener('click', () => openModal(trigger));
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      closeModal();
      return;
    }
    const key = e.target.closest('.pin-key[data-key]');
    if (key) pressDigit(key.dataset.key);
  });
  backspaceBtn.addEventListener('click', pressBackspace);
  cancelBtn.addEventListener('click', closeModal);

  // Progressive enhancement for desktop: physical number keys work too.
  // This never focuses an <input>, so it doesn't change mobile behavior —
  // touch devices simply won't fire keydown from a hardware keyboard.
  document.addEventListener('keydown', (e) => {
    if (!overlay.classList.contains('open')) return;
    if (e.key >= '0' && e.key <= '9') pressDigit(e.key);
    else if (e.key === 'Backspace') pressBackspace();
    else if (e.key === 'Escape') closeModal();
  });

  // If the server re-rendered this page after a wrong PIN (see the view's
  // handling of InvalidPinError), reopen the modal already in error state
  // instead of making the person find and re-click the trigger button.
  if (document.body.dataset.pinError === '1') {
    const trigger = document.querySelector('.js-pin-trigger');
    if (trigger) {
      openModal(trigger);
      showError(document.body.dataset.pinErrorMessage);
    }
  }
})();
