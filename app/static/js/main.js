/* ============================================================
   Tata Power EZ Charge — EV Network Management Demo
   Client Interactions, Collapsible Sidebar & Dropdown Helpers
   ============================================================ */

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.style.display = 'none';
  }
}

function toggleProfileMenu(btn) {
  const wrap = btn.closest('.profile-menu-wrap');
  if (!wrap) return;
  const menu = wrap.querySelector('.profile-dropdown');
  if (menu) {
    menu.classList.toggle('open');
  }
}

function toggleAdminSidebar() {
  if (window.innerWidth <= 1120) {
    document.body.classList.toggle('sidebar-mobile-open');
  } else {
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    try {
      localStorage.setItem('ev_sidebar_collapsed', collapsed ? '1' : '0');
    } catch (e) { /* storage disabled */ }
  }
}

function closeMobileSidebar() {
  document.body.classList.remove('sidebar-mobile-open');
}

// Close modals & profile dropdowns when clicking outside
window.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
  }
  if (!e.target.closest('.profile-menu-wrap')) {
    document.querySelectorAll('.profile-dropdown.open').forEach((el) => el.classList.remove('open'));
  }
});

// Restore sidebar state & auto-dismiss alert banners
document.addEventListener('DOMContentLoaded', () => {
  try {
    if (localStorage.getItem('ev_sidebar_collapsed') === '1' && window.innerWidth > 1120) {
      document.body.classList.add('sidebar-collapsed');
    }
  } catch (e) { /* ignore */ }

  const alerts = document.querySelectorAll('.alert');
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => alert.remove(), 400);
    }, 6000);
  });
});
