/* Snapshot previews never embed or start the linked robot workspaces. */
(() => {
  'use strict';
  const preview = document.getElementById('preview');
  if (!preview || typeof preview.showModal !== 'function') return;
  const image = document.getElementById('previewImage');
  let opener = null;
  for (const link of document.querySelectorAll('[data-preview]')) {
    link.addEventListener('click', event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = link;
      document.getElementById('previewTitle').textContent = link.querySelector('h2').textContent;
      document.getElementById('previewDescription').textContent = link.querySelector('p').textContent;
      image.src = link.querySelector('img').src;
      image.alt = link.querySelector('img').alt;
      document.getElementById('visitWebsite').href = link.href;
      preview.showModal();
      preview.querySelector('.previewImage').scrollTop = 0;
    });
  }
  preview.querySelector('.closePreview').addEventListener('click', () => preview.close());
  // Close only if both ends of a pointer action are on the backdrop.
  let backdropDown = false;
  const outside = event => {
    const r = preview.getBoundingClientRect();
    return event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom;
  };
  preview.addEventListener('pointerdown', event => { backdropDown = event.target === preview && outside(event); });
  preview.addEventListener('click', event => {
    if (backdropDown && event.target === preview && outside(event)) preview.close();
    backdropDown = false;
  });
  preview.addEventListener('close', () => { opener?.focus({preventScroll:true}); });
})();
