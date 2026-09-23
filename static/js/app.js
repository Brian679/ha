document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.querySelector('[data-sidebar]');
  const overlay = document.querySelector('[data-sidebar-overlay]');
  const openSidebar = () => { if (sidebar) sidebar.classList.add('open'); if (overlay) overlay.classList.add('show'); };
  const closeSidebar = () => { if (sidebar) sidebar.classList.remove('open'); if (overlay) overlay.classList.remove('show'); };
  document.querySelector('[data-sidebar-open]')?.addEventListener('click', openSidebar);
  document.querySelector('[data-sidebar-close]')?.addEventListener('click', closeSidebar);
  overlay?.addEventListener('click', closeSidebar);
  const menu = document.querySelector('[data-menu]');
  document.querySelector('[data-menu-toggle]')?.addEventListener('click', () => menu?.classList.toggle('open'));
  document.querySelectorAll('.flash').forEach((flash) => setTimeout(() => { flash.style.opacity = '0'; flash.style.transition = 'opacity .4s'; }, 5000));
  document.addEventListener('keydown', (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); document.querySelector('.global-search input')?.focus(); } });
  document.querySelectorAll('.clickable-row[data-href]').forEach((row) => row.addEventListener('click', (event) => { if (!event.target.closest('button,a,form')) window.location = row.dataset.href; }));
});
