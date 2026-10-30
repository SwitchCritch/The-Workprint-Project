(function () {
  'use strict';
  const wrapper = document.querySelector('[data-rich-editor]');
  if (!wrapper) return;
  const editor = wrapper.querySelector('.rich-edit-area');
  const source = wrapper.querySelector('textarea[name="differences"]');
  const form = wrapper.closest('form');
  if (!editor || !source || !form) return;

  const sync = () => { source.value = editor.innerHTML.trim(); };
  const focus = () => editor.focus();
  // Retain selected text when a toolbar button is clicked.
  wrapper.querySelector('.rich-toolbar')?.addEventListener('mousedown', (event) => {
    if (event.target.closest('button')) event.preventDefault();
  });
  wrapper.querySelectorAll('[data-command]').forEach(btn => btn.addEventListener('click', () => {
    focus();
    document.execCommand(btn.dataset.command, false, null);
    sync();
  }));
  wrapper.querySelectorAll('[data-block]').forEach(btn => btn.addEventListener('click', () => {
    focus();
    document.execCommand('formatBlock', false, btn.dataset.block);
    sync();
  }));
  const link = wrapper.querySelector('[data-link]');
  if (link) link.addEventListener('click', () => {
    const selection = window.getSelection();
    if (!selection || !selection.toString().trim()) {
      alert('Select some text in the editor before adding a link.');
      return;
    }
    const selectedRange = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    const url = prompt('Enter an HTTPS link (or leave blank to cancel):', 'https://');
    if (!url) return;
    if (!/^https?:\/\/[^\s]+$/i.test(url.trim())) {
      alert('Please enter a valid http:// or https:// address.');
      return;
    }
    focus();
    if (selectedRange) {
      selection.removeAllRanges();
      selection.addRange(selectedRange);
    }
    document.execCommand('createLink', false, url.trim());
    sync();
  });
  editor.addEventListener('input', sync);
  editor.addEventListener('blur', sync);
  editor.addEventListener('paste', (event) => {
    // Strip markup copied from external sites; this also avoids pasted scripts and styling.
    const pasted = event.clipboardData && event.clipboardData.getData('text/plain');
    if (typeof pasted === 'string' && pasted.length) {
      event.preventDefault();
      document.execCommand('insertText', false, pasted);
      sync();
    }
  });
  form.addEventListener('submit', sync);
  sync();
})();
