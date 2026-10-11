// Context help shares one native popover, so panels cannot clip it. The
// browser handles Escape and outside clicks; all content is plain text.
import { esc } from './util.js';

export function help(key, label, text) {
  return '<button type="button" class="help-trigger" data-key="help-' + esc(key)
    + '" data-help="' + esc(text) + '" data-help-title="' + esc(label)
    + '" aria-label="About ' + esc(label) + '" aria-expanded="false" aria-controls="context-help">'
    + '<span aria-hidden="true"></span></button>';
}

export function mountHelp() {
  const popup = document.createElement('div');
  popup.id = 'context-help';
  popup.className = 'help-popover';
  popup.setAttribute('popover', 'auto');
  popup.setAttribute('role', 'tooltip');
  const title = document.createElement('strong');
  const body = document.createElement('p');
  popup.append(title, body);
  document.body.append(popup);
  let trigger = null;
  let timer;
  const reset = () => {
    if (trigger) {
      trigger.setAttribute('aria-expanded', 'false');
      trigger.removeAttribute('aria-describedby');
    }
    trigger = null;
  };
  const close = () => {
    clearTimeout(timer);
    if (popup.matches(':popover-open')) popup.hidePopover();
    reset();
  };
  const show = (button) => {
    clearTimeout(timer);
    if (trigger !== button) reset();
    trigger = button;
    title.textContent = button.dataset.helpTitle;
    body.textContent = button.dataset.help;
    popup.showPopover();
    button.setAttribute('aria-expanded', 'true');
    button.setAttribute('aria-describedby', popup.id);
    const rect = button.getBoundingClientRect();
    popup.style.left = Math.max(8, Math.min(rect.left, innerWidth - popup.offsetWidth - 8)) + 'px';
    popup.style.top = Math.max(8, rect.bottom + popup.offsetHeight + 8 <= innerHeight
      ? rect.bottom + 8 : rect.top - popup.offsetHeight - 8) + 'px';
  };
  for (const event of ['pointerover', 'focusin', 'click']) {
    document.addEventListener(event, (e) => {
      const button = e.target.closest('.help-trigger');
      if (button && !button.contains(e.relatedTarget)) show(button);
    });
  }
  for (const event of ['pointerout', 'focusout']) {
    document.addEventListener(event, (e) => {
      if (!trigger || (!trigger.contains(e.target) && !popup.contains(e.target))) return;
      if (trigger.contains(e.relatedTarget) || popup.contains(e.relatedTarget)) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (trigger && !trigger.matches(':hover') && !popup.matches(':hover')
          && document.activeElement !== trigger) close();
      }, 160);
    });
  }
  popup.addEventListener('beforetoggle', (e) => { if (e.newState === 'closed') reset(); });
  document.addEventListener('scroll', close, true);
  window.addEventListener('resize', close);
  return close;
}
