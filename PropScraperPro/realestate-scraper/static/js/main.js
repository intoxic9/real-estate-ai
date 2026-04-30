// PropScraper Pro — main.js
// Utility functions available on all pages

// Auto-refresh active job rows in dashboard
document.addEventListener('DOMContentLoaded', () => {
  // Highlight active nav link
  const path = window.location.pathname;

  // Animate stat numbers on homepage
  document.querySelectorAll('.hstat-n').forEach(el => {
    const target = parseInt(el.textContent.replace(/,/g, ''), 10);
    if (!isNaN(target) && target > 0) animateCount(el, 0, target, 800);
  });
});

function animateCount(el, start, end, duration) {
  const step = (end - start) / (duration / 16);
  let current = start;
  const timer = setInterval(() => {
    current += step;
    if (current >= end) { current = end; clearInterval(timer); }
    el.textContent = Math.floor(current).toLocaleString();
  }, 16);
}

// Toast notification system
function showToast(msg, type = 'info') {
  const colors = { info: '#3b82f6', success: '#10b981', error: '#ef4444' };
  const toast = document.createElement('div');
  toast.style.cssText = `
    position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;
    padding:.75rem 1.25rem;border-radius:10px;
    background:${colors[type]};color:#fff;
    font-size:.875rem;font-weight:500;
    box-shadow:0 4px 20px rgba(0,0,0,.4);
    transform:translateY(60px);opacity:0;
    transition:all .25s ease;pointer-events:none;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  requestAnimationFrame(() => {
    toast.style.transform = 'translateY(0)';
    toast.style.opacity = '1';
  });
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(30px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
