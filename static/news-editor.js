(() => {
  const editor = document.getElementById('news-editor');
  if (!editor) return;
  const output = document.getElementById('article-body');
  const form = editor.closest('form');
  const insertButton = document.getElementById('insert-youtube');
  if (!output || !form) return;
  let savedRange = null;
  const sync = () => { output.value = editor.innerHTML; };
  const hasCursor = (node) => node && (node === editor || editor.contains(node));
  const rememberCursor = () => {
    const selection = window.getSelection();
    if (selection && selection.rangeCount && hasCursor(selection.anchorNode)) {
      savedRange = selection.getRangeAt(0).cloneRange();
    }
  };
  editor.addEventListener('keyup', rememberCursor);
  editor.addEventListener('mouseup', rememberCursor);
  editor.addEventListener('input', () => { rememberCursor(); sync(); });
  editor.addEventListener('focus', rememberCursor);
  form.addEventListener('submit', sync);

  // Support standard YouTube links, short links, Shorts, Live and embed links.
  function videoId(input) {
    try {
      const url = new URL(input.trim());
      const host = url.hostname.toLowerCase();
      let id = '';
      if (host === 'youtu.be' || host === 'www.youtu.be') {
        id = url.pathname.split('/').filter(Boolean)[0] || '';
      } else if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'].includes(host)) {
        const segments = url.pathname.split('/').filter(Boolean);
        if (segments[0] === 'watch') id = url.searchParams.get('v') || '';
        else if (['embed', 'shorts', 'live', 'v'].includes(segments[0])) id = segments[1] || '';
      }
      return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
    } catch { return null; }
  }
  function decorateVideoMarkers() {
    editor.querySelectorAll('span.youtube-embed[data-youtube-id]').forEach(marker => {
      if (!/^[A-Za-z0-9_-]{11}$/.test(marker.dataset.youtubeId || '')) return;
      marker.contentEditable = 'false';
      marker.setAttribute('role', 'button');
      marker.setAttribute('tabindex', '0');
      marker.setAttribute('title', 'Click to remove or replace video');
      marker.textContent = '▶ YouTube video · ' + marker.dataset.youtubeId + '   ✎';
    });
  }
  decorateVideoMarkers();
  editor.addEventListener('click', e => {
    const marker = e.target.closest('span.youtube-embed');
    if (!marker || !editor.contains(marker)) return;
    const answer = prompt('Replace this video with a new YouTube link, or leave blank to remove it:', 'https://youtu.be/' + marker.dataset.youtubeId);
    if (answer === null) return;
    if (!answer.trim()) marker.remove();
    else {
      const id = videoId(answer);
      if (!id) { alert('Please provide a valid YouTube video URL.'); return; }
      marker.dataset.youtubeId = id;
      decorateVideoMarkers();
    }
    sync();
  });
  editor.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('span.youtube-embed')) {
      e.preventDefault(); e.target.click();
    }
  });
  editor.closest('.editor-box').querySelectorAll('[data-format]').forEach(button => {
    button.addEventListener('mousedown', e => e.preventDefault());
    button.addEventListener('click', () => {
      editor.focus();
      const action = button.dataset.format;
      if (action === 'h2') document.execCommand('formatBlock', false, 'h2');
      else if (action === 'ul' || action === 'ol') document.execCommand(action === 'ul' ? 'insertUnorderedList' : 'insertOrderedList', false, null);
      else if (action === 'link') {
        const url = prompt('Enter an HTTPS link:');
        if (url && /^https:\/\//i.test(url)) document.execCommand('createLink', false, url);
      } else document.execCommand(action, false, null);
      sync();
    });
  });
  if (insertButton) {
    insertButton.addEventListener('mousedown', e => e.preventDefault());
    insertButton.addEventListener('click', () => {
      rememberCursor();
      const input = prompt('Paste a YouTube video URL (watch, share, Shorts or live):');
      if (input === null) return;
      const id = videoId(input);
      if (!id) { alert('Invalid YouTube link. Paste a complete YouTube video URL.'); return; }
      editor.focus();
      const selection = window.getSelection();
      if (savedRange && selection) {
        selection.removeAllRanges();
        selection.addRange(savedRange);
      }
      const marker = document.createElement('span');
      marker.className = 'youtube-embed';
      marker.dataset.youtubeId = id;
      marker.textContent = '▶ YouTube video · ' + id + '   ✎';
      marker.contentEditable = 'false';
      const block = document.createElement('p');
      block.className = 'editor-video-block';
      block.appendChild(marker);
      // Insert at current cursor; never require pasting HTML or editing source.
      document.execCommand('insertHTML', false, block.outerHTML + '<p><br></p>');
      decorateVideoMarkers();
      rememberCursor();
      sync();
    });
  }
  sync();
})();
