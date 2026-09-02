/**
 * TarGz Manager - Frontend SPA Application
 * Pure Vanilla JavaScript with Zero External Dependencies
 */

class TarGzApp {
  constructor() {
    this.apps = [];
    this.discoveredApps = [];
    this.stats = {};
    this.systemInfo = {};
    this.currentTab = 'all';
    this.currentSort = 'name_asc';
    this.searchQuery = '';
    
    // Wizard State
    this.currentInstallStep = 1;
    this.activeInspection = null;
    this.selectedExecRelPath = null;
    this.selectedIconRelPath = null;
    
    // Browser Modal State
    this.browserMode = 'all';
    this.browserTargetInputId = null;
    this.browserOnSelectCallback = null;
    this.browserCurrentPath = '';
    this.browserSelectedItem = null;
    
    // Active App in Focus (for edit/update/uninstall)
    this.activeApp = null;
    this.clientId = 'client_' + Math.random().toString(36).substring(2, 10);

    // Clean Master State
    this.cleanerData = null;
    this.selectedCleanerTargets = new Set();
    this.pendingSudoTargets = [];
    this.isCleaning = false;

    this.init();
  }

  async init() {
    this.setupTheme();
    this.setupEventListeners();
    this.startHeartbeat();
    await this.fetchSystemInfo();
    await this.refreshApps();
    await this.refreshStats();
    await this.fetchDiscovered();
    this.scanCleaner(false);
  }

  startHeartbeat() {
    const sendPing = () => {
      fetch('/api/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: this.clientId })
      }).catch(() => {});
    };

    sendPing();
    setInterval(sendPing, 2500);

    window.addEventListener('pagehide', () => {
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/shutdown', JSON.stringify({ client_id: this.clientId }));
      }
    });
  }

  // =========================================================================
  // Theme & Event Listeners
  // =========================================================================
  setupTheme() {
    const savedTheme = localStorage.getItem('targz_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    this.updateThemeIcon(savedTheme);
  }

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('targz_theme', next);
    this.updateThemeIcon(next);
  }

  updateThemeIcon(theme) {
    const btn = document.getElementById('themeToggleBtn');
    if (!btn) return;
    if (theme === 'dark') {
      btn.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>`;
    } else {
      btn.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`;
    }
  }

  setupEventListeners() {
    // Search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.trim();
        this.renderApps();
      });
    }

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchInput?.focus();
      }
      if (e.key === 'Escape') {
        this.closeAllModals();
      }
    });

    // Drag and Drop Zone
    const dropzone = document.getElementById('archiveDropzone');
    if (dropzone) {
      ['dragenter', 'dragover'].forEach(name => {
        dropzone.addEventListener(name, (e) => {
          e.preventDefault();
          dropzone.classList.add('drag-active');
        });
      });
      ['dragleave', 'drop'].forEach(name => {
        dropzone.addEventListener(name, (e) => {
          e.preventDefault();
          dropzone.classList.remove('drag-active');
        });
      });
      dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
          this.uploadFile(files[0]);
        }
      });
    }

    // Modal backdrop clicks
    document.querySelectorAll('.modal-backdrop').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          this.closeModal(modal.id);
        }
      });
    });
  }

  // =========================================================================
  // API Calls & Data Fetching
  // =========================================================================
  async fetchSystemInfo() {
    try {
      const res = await fetch('/api/system-info');
      if (res.ok) {
        this.systemInfo = await res.json();
      }
    } catch (e) {
      console.error('Failed to load system info:', e);
    }
  }

  async refreshApps() {
    try {
      const res = await fetch(`/api/apps?sort=${encodeURIComponent(this.currentSort)}`);
      if (res.ok) {
        const data = await res.json();
        this.apps = data.apps || [];
        const countAll = document.getElementById('countAllApps');
        if (countAll) countAll.innerText = this.apps.filter(a => !a.ignored).length;
        this.updateIgnoredCount();
        this.renderApps();
      }
    } catch (e) {
      this.toast('Error fetching applications', 'error');
    }
  }

  async refreshStats() {
    try {
      const res = await fetch('/api/stats');
      if (res.ok) {
        const data = await res.json();
        this.stats = data.stats || {};
      }
    } catch (e) {
      console.error('Failed to load stats:', e);
    }
  }

  async refreshAll() {
    this.toast('Scanning system and refreshing...', 'info');
    await this.refreshApps();
    await this.refreshStats();
    await this.fetchDiscovered();
    this.toast('Refreshed!', 'success');
  }

  // =========================================================================
  // Auto-Discovery of Manual Applications
  // =========================================================================
  async fetchDiscovered() {
    try {
      const res = await fetch('/api/discovered');
      if (res.ok) {
        const data = await res.json();
        this.discoveredApps = data.discovered || [];
        this.renderDiscoveredBanner();
        this.updateIgnoredCount();
      }
    } catch (e) {
      console.error('Discovery fetch error:', e);
    }
  }

  renderDiscoveredBanner() {
    const banner = document.getElementById('discoveredBanner');
    const tabPill = document.getElementById('discoveredTabPill');
    const countPill = document.getElementById('discoveredCountPill');
    const pillTabCount = document.getElementById('pillDiscoveredCount');
    const bannerText = document.getElementById('discoveredBannerText');

    const available = this.getActiveDiscovered();

    if (!banner || !tabPill) return;

    if (available.length > 0) {
      banner.style.display = 'flex';
      tabPill.style.display = 'inline-flex';
      if (countPill) countPill.innerText = available.length;
      if (pillTabCount) pillTabCount.innerText = available.length;
      if (bannerText) {
        bannerText.innerText = `Found ${available.length} manual application(s) or tarballs in /opt, ~/Applications, or desktop shortcuts ready to be managed.`;
      }
    } else {
      banner.style.display = 'none';
      tabPill.style.display = 'none';
      if (this.currentTab === 'discovered') {
        this.setTab('all');
      }
    }
  }

  getActiveDiscovered() {
    return this.discoveredApps.filter(item => !item.ignored);
  }

  updateIgnoredCount() {
    const count = this.apps.filter(a => a.ignored).length + this.discoveredApps.filter(d => d.ignored).length;
    const el = document.getElementById('countIgnored');
    if (el) el.innerText = count;
  }

  dismissDiscoveredBanner() {
    const banner = document.getElementById('discoveredBanner');
    if (banner) banner.style.display = 'none';
  }

  async ignoreDiscovered(index) {
    const item = this.discoveredApps[index];
    if (!item) return;
    try {
      const res = await fetch('/api/discovered/ignore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: item.ignore_key, display_name: item.display_name })
      });
      if (res.ok) {
        item.ignored = true;
        this.renderDiscoveredBanner();
        this.updateIgnoredCount();
        this.renderApps();
        this.toast('Moved to Ignored', 'info');
      }
    } catch (e) {
      this.toast('Error ignoring item: ' + e.message, 'error');
    }
  }

  async unignoreDiscovered(index) {
    const item = this.discoveredApps[index];
    if (!item) return;
    try {
      const res = await fetch('/api/discovered/unignore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: item.ignore_key })
      });
      if (res.ok) {
        item.ignored = false;
        this.renderDiscoveredBanner();
        this.updateIgnoredCount();
        this.renderApps();
        this.toast('Restored to Discovered', 'success');
      }
    } catch (e) {
      this.toast('Error restoring item: ' + e.message, 'error');
    }
  }

  async toggleIgnoreApp(appId, ignore) {
    try {
      const res = await fetch(`/api/apps/${appId}/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ignored: ignore })
      });
      if (res.ok) {
        this.toast(ignore ? 'App moved to Ignored' : 'App restored', ignore ? 'info' : 'success');
        await this.refreshApps();
      }
    } catch (e) {
      this.toast('Error updating app: ' + e.message, 'error');
    }
  }

  async addSingleDiscovered(index) {
    const item = this.discoveredApps[index];
    if (!item) return;

    this.toast(`Adding ${item.display_name} to manager...`, 'info');
    try {
      const res = await fetch('/api/discovered/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`${data.app.display_name} added to managed apps!`, 'success');
        await this.refreshApps();
        await this.refreshStats();
        await this.fetchDiscovered();
      } else {
        this.toast(data.error || 'Failed to add application', 'error');
      }
    } catch (e) {
      this.toast('Error adding application: ' + e.message, 'error');
    }
  }

  async addAllDiscovered() {
    const available = this.getActiveDiscovered();
    if (available.length === 0) return;

    this.toast(`Adding all ${available.length} applications...`, 'info');
    let added = 0;
    for (let i = 0; i < this.discoveredApps.length; i++) {
      if (this.discoveredApps[i].ignored) continue;
      const item = this.discoveredApps[i];
      try {
        const res = await fetch('/api/discovered/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(item)
        });
        if (res.ok) added++;
      } catch (e) {}
    }

    this.toast(`Successfully added ${added} applications!`, 'success');
    await this.refreshApps();
    await this.refreshStats();
    await this.fetchDiscovered();
    this.setTab('all');
  }

  reviewDiscovered(index) {
    const item = this.discoveredApps[index];
    if (!item) return;

    if (item.is_tarball_archive && item.archive_path) {
      this.openInstallWizard();
      document.getElementById('installArchivePath').value = item.archive_path;
      this.inspectArchive(item.archive_path);
    } else {
      this.openRegisterModal();
      document.getElementById('regInstallPath').value = item.install_path;
      document.getElementById('regExecutablePath').value = item.executable_path || '';
      document.getElementById('regName').value = item.name || '';
      document.getElementById('regDisplayName').value = item.display_name || '';
      document.getElementById('regVersion').value = item.version || '1.0.0';
      document.getElementById('regDescription').value = item.description || '';
      document.getElementById('regIconPath').value = item.icon_path || '';
      this.onRegisterDirChanged();
    }
  }

  // =========================================================================
  // Navigation & Search Handling
  // =========================================================================
  setTab(tab) {
    this.currentTab = tab;
    const tabAll = document.getElementById('tabAllApps');
    const tabDisc = document.getElementById('discoveredTabPill');
    const tabIgnored = document.getElementById('tabIgnored');
    const tabCleaner = document.getElementById('tabCleaner');
    const viewSortControls = document.getElementById('viewSortControls');
    const appsGrid = document.getElementById('appsGrid');
    const emptyState = document.getElementById('emptyState');
    const cleanerView = document.getElementById('cleanerView');

    if (tabAll) tabAll.classList.toggle('active', tab === 'all');
    if (tabDisc) tabDisc.classList.toggle('active', tab === 'discovered');
    if (tabIgnored) tabIgnored.classList.toggle('active', tab === 'ignored');
    if (tabCleaner) tabCleaner.classList.toggle('active', tab === 'cleaner');

    if (tab === 'cleaner') {
      if (appsGrid) appsGrid.style.display = 'none';
      if (emptyState) emptyState.style.display = 'none';
      if (viewSortControls) viewSortControls.style.display = 'none';
      if (cleanerView) cleanerView.style.display = 'flex';
      this.scanCleaner(false);
    } else {
      if (cleanerView) cleanerView.style.display = 'none';
      if (viewSortControls) viewSortControls.style.display = 'flex';
      if (appsGrid) appsGrid.style.display = 'grid';
      this.renderApps();
    }
  }

  setSort(sortVal) {
    this.currentSort = sortVal;
    this.refreshApps();
  }

  getFilteredApps() {
    if (this.currentTab === 'discovered') {
      return this.getActiveDiscovered();
    }

    if (this.currentTab === 'ignored') {
      return [
        ...this.apps.filter(a => a.ignored),
        ...this.discoveredApps.filter(d => d.ignored)
      ];
    }

    let filtered = this.apps.filter(a => !a.ignored);
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase();
      filtered = filtered.filter(a =>
        a.name.toLowerCase().includes(q) ||
        (a.display_name && a.display_name.toLowerCase().includes(q)) ||
        (a.description && a.description.toLowerCase().includes(q))
      );
    }
    return filtered;
  }

  // =========================================================================
  // Render Applications Grid
  // =========================================================================
  renderApps() {
    const grid = document.getElementById('appsGrid');
    const emptyState = document.getElementById('emptyState');
    const list = this.getFilteredApps();

    if (!list || list.length === 0) {
      grid.innerHTML = '';
      emptyState.style.display = 'block';
      const title = document.getElementById('emptyStateTitle');
      const desc = document.getElementById('emptyStateDesc');
      const actions = document.getElementById('emptyStateActions');
      if (this.currentTab === 'ignored') {
        if (title) title.innerText = 'Nothing Ignored';
        if (desc) desc.innerText = 'Apps and discovered suggestions you ignore will show up here, and you can restore them anytime.';
        if (actions) actions.style.display = 'none';
      } else {
        if (title) title.innerText = 'No Applications Managed Yet';
        if (desc) desc.innerHTML = 'Install a <code>.tar.gz</code> / <code>.tar.xz</code> binary archive or register apps you already extracted by hand to organize them, generate desktop shortcuts, and manage clean upgrades & removals.';
        if (actions) actions.style.display = 'flex';
      }
      return;
    }

    emptyState.style.display = 'none';

    if (this.currentTab === 'discovered') {
      grid.innerHTML = this.discoveredApps.map((item, idx) => {
        return item.ignored ? '' : this.renderDiscoveredCard(item, idx);
      }).join('');
    } else if (this.currentTab === 'ignored') {
      const ignoredAppsHtml = this.apps.filter(a => a.ignored).map(app => this.renderAppCard(app)).join('');
      const ignoredDiscoveredHtml = this.discoveredApps.map((item, idx) => {
        return item.ignored ? this.renderDiscoveredCard(item, idx) : '';
      }).join('');
      grid.innerHTML = ignoredAppsHtml + ignoredDiscoveredHtml;
    } else {
      grid.innerHTML = list.map(app => this.renderAppCard(app)).join('');
    }
  }

  renderDiscoveredCard(item, idx) {
    const iconUrl = item.icon_path
      ? `/api/icons/view?path=${encodeURIComponent(item.icon_path)}`
      : null;

    const iconHtml = iconUrl
      ? `<img src="${iconUrl}" onerror="this.onerror=null; this.parentElement.innerText='${this.getMonogram(item.display_name)}';" alt="${this.escapeHtml(item.display_name)}">`
      : this.getMonogram(item.display_name);

    const sudoBadge = item.needs_sudo
      ? `<span class="badge badge-sudo" title="Root/Sudo permissions required to modify files in this directory"><svg class="icon" style="width:11px;height:11px;" viewBox="0 0 24 24"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> /opt Root</span>`
      : '';

    return `
      <div class="app-card discovered-card" id="discovered-card-${idx}">
        <div>
          <div class="app-card-header">
            <div class="app-icon">
              ${iconHtml}
            </div>
            <div class="app-title-area">
              <div class="app-name-row">
                <h4 class="app-name" title="${this.escapeHtml(item.display_name)}">${this.escapeHtml(item.display_name)}</h4>
                <span class="badge badge-indigo" style="font-size:0.65rem;">Discovered</span>
              </div>
              <div class="app-meta-row">
                <span class="badge badge-slate">${this.escapeHtml(item.version || '1.0.0')}</span>
                <span class="badge badge-slate" style="font-size:0.7rem;">${item.size_formatted}</span>
                ${sudoBadge}
              </div>
            </div>
          </div>

          <div class="app-description" title="${this.escapeHtml(item.description || item.discovery_reason || '')}">
            <strong>${this.escapeHtml(item.discovery_reason || 'Unmanaged manual application')}</strong>
            ${item.description ? `<br>${this.escapeHtml(item.description)}` : ''}
          </div>

          <div class="app-paths-info">
            <div class="path-line" title="${this.escapeHtml(item.install_path || item.archive_path)}">
              <span class="path-line-label">LOC:</span>
              <span>${this.escapeHtml(this.shortenPath(item.install_path || item.archive_path))}</span>
            </div>
            ${item.executable_path ? `
              <div class="path-line" title="${this.escapeHtml(item.executable_path)}">
                <span class="path-line-label">BIN:</span>
                <span>${this.escapeHtml(this.shortenPath(item.executable_path))}</span>
              </div>
            ` : ''}
          </div>
        </div>

        <div class="app-actions">
          <div class="actions-left">
            <button class="btn btn-sm btn-success" onclick="app.addSingleDiscovered(${idx})" title="1-Click Add to Database">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
              ${item.is_tarball_archive ? 'Install Tarball' : 'Add to Manager'}
            </button>
          </div>
          <div class="actions-right">
            <button class="btn btn-sm btn-secondary" onclick="app.reviewDiscovered(${idx})" title="Review and customize">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              Review
            </button>
            ${item.ignored
              ? `<button class="btn btn-sm btn-secondary" onclick="app.unignoreDiscovered(${idx})" title="Move back to Discovered">Unignore</button>`
              : `<button class="btn btn-sm btn-icon" onclick="app.ignoreDiscovered(${idx})" title="Ignore this suggestion">✕</button>`
            }
          </div>
        </div>
      </div>
    `;
  }

  renderAppCard(app) {
    const iconHtml = app.icon_path && app.icon_exists
      ? `<img src="${encodeURI('/api/apps/' + app.id + '/icon?t=' + Date.now())}" onerror="this.onerror=null; this.parentElement.innerText='${this.getMonogram(app.display_name)}';" alt="${this.escapeHtml(app.display_name)}">`
      : this.getMonogram(app.display_name);

    const statusDotClass = app.status_color || 'green';
    const statusTip = app.status_message || 'Operational';

    const sudoBadge = app.needs_sudo
      ? `<span class="badge badge-sudo" title="Installed in root-protected directory (${this.shortenPath(app.install_path)}). Sudo / PolicyKit password required to update or delete."><svg class="icon" style="width:11px;height:11px;" viewBox="0 0 24 24"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> Sudo Required</span>`
      : '';

    return `
      <div class="app-card" id="app-card-${app.id}">
        <div>
          <div class="app-card-header">
            <div class="app-icon">
              ${iconHtml}
            </div>
            <div class="app-title-area">
              <div class="app-name-row">
                <h4 class="app-name" title="${this.escapeHtml(app.display_name)}">${this.escapeHtml(app.display_name)}</h4>
                <div class="status-dot ${statusDotClass}" title="${this.escapeHtml(statusTip)}"></div>
              </div>
              <div class="app-meta-row">
                <span class="badge badge-slate">v${this.escapeHtml(app.version || '1.0.0')}</span>
                <span class="badge badge-slate" style="font-size:0.7rem;">${app.size_formatted}</span>
                ${sudoBadge}
              </div>
            </div>
          </div>

          <div class="app-description" title="${this.escapeHtml(app.description || '')}">
            ${this.escapeHtml(app.description || 'Portable tarball application managed with TarGz Manager.')}
          </div>

          <div class="app-paths-info">
            <div class="path-line" title="${this.escapeHtml(app.install_path)}">
              <span class="path-line-label">DIR:</span>
              <span>${this.escapeHtml(this.shortenPath(app.install_path))}</span>
            </div>
            <div class="path-line" title="${this.escapeHtml(app.executable_path)}">
              <span class="path-line-label">BIN:</span>
              <span>${this.escapeHtml(this.shortenPath(app.executable_path))}</span>
            </div>
          </div>

          <div class="app-tags">
            ${app.desktop_entry_path && app.desktop_exists ? `
              <span class="badge badge-emerald" title="Desktop launcher active">
                <svg class="icon" style="width:12px;height:12px;" viewBox="0 0 24 24"><rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/></svg>
                Desktop Shortcut
              </span>
            ` : ''}
            ${app.symlink_path && app.symlink_exists ? `
              <span class="badge badge-emerald" title="Terminal symlink in PATH active">
                <svg class="icon" style="width:12px;height:12px;" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
                $PATH: ${this.escapeHtml(app.name)}
              </span>
            ` : ''}
            ${app.source_type === 'registered' ? `
              <span class="badge badge-slate" title="Pre-existing registered app">Registered</span>
            ` : ''}
          </div>
        </div>

        <div class="app-actions">
          <div class="actions-left">
            <button class="btn btn-sm btn-primary" onclick="app.launchApp(${app.id})" title="Launch Application">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Launch
            </button>
            <button class="btn btn-sm btn-secondary" onclick="app.openFolder(${app.id})" title="Open Directory in File Manager">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>
              Folder
            </button>
          </div>
          <div class="actions-right">
            <button class="btn btn-sm btn-secondary" onclick="app.openUpdateModal(${app.id})" title="Update with new tarball">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
            </button>
            <button class="btn btn-sm btn-secondary" onclick="app.openDetailsModal(${app.id})" title="Configure & Edit">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            </button>
            <button class="btn btn-sm btn-secondary" onclick="app.toggleIgnoreApp(${app.id}, ${app.ignored ? 'false' : 'true'})" title="${app.ignored ? 'Restore from Ignored' : 'Ignore this app'}">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="app.openUninstallModal(${app.id})" title="Uninstall Application">
              <svg class="icon" style="width:14px;height:14px;" viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // =========================================================================
  // Quick Actions: Launch, Open Folder
  // =========================================================================
  async launchApp(appId) {
    try {
      const res = await fetch(`/api/apps/${appId}/launch`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast('Application launched successfully', 'success');
      } else {
        this.toast(data.error || 'Failed to launch application', 'error');
      }
    } catch (e) {
      this.toast('Error launching application', 'error');
    }
  }

  async openFolder(appId) {
    try {
      const res = await fetch(`/api/apps/${appId}/open-folder`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast('Folder opened in file manager', 'info');
      } else {
        this.toast(data.error || 'Failed to open directory', 'error');
      }
    } catch (e) {
      this.toast('Error opening directory', 'error');
    }
  }

  // =========================================================================
  // Install Tarball Wizard
  // =========================================================================
  openInstallWizard() {
    this.currentInstallStep = 1;
    this.activeInspection = null;
    this.selectedExecRelPath = null;
    this.selectedIconRelPath = null;

    document.getElementById('installArchivePath').value = '';
    document.getElementById('inspectionPreviewBox').style.display = 'none';
    document.getElementById('installDisplayName').value = '';
    document.getElementById('installSlugName').value = '';
    document.getElementById('installVersion').value = '';
    document.getElementById('installDestinationPath').value = '';
    document.getElementById('installDescription').value = '';
    document.getElementById('installNotes').value = '';
    document.getElementById('installExecCustomPath').value = '';
    document.getElementById('installIconCustomPath').value = '';
    document.getElementById('installCreateDesktop').checked = true;
    document.getElementById('installCreateSymlink').checked = true;
    document.getElementById('installFlattenWrapper').checked = true;
    document.getElementById('installTerminal').checked = false;

    this.showInstallStep(1);
    this.openModal('installModal');
  }

  showInstallStep(stepNum) {
    this.currentInstallStep = stepNum;
    for (let i = 1; i <= 4; i++) {
      const content = document.getElementById(`installStep${i}`);
      const indicator = document.getElementById(`stepIndicator${i}`);
      if (content) content.style.display = i === stepNum ? 'block' : 'none';
      if (indicator) {
        indicator.classList.toggle('active', i === stepNum);
        indicator.classList.toggle('completed', i < stepNum);
      }
    }

    const prevBtn = document.getElementById('wizardPrevBtn');
    const nextBtn = document.getElementById('wizardNextBtn');
    const submitBtn = document.getElementById('wizardSubmitBtn');

    if (prevBtn) prevBtn.style.display = stepNum > 1 ? 'inline-flex' : 'none';
    if (nextBtn) {
      nextBtn.style.display = stepNum < 4 ? 'inline-flex' : 'none';
      if (stepNum === 1) nextBtn.innerText = 'Next: App Details';
      else if (stepNum === 2) nextBtn.innerText = 'Next: Executable & Icon';
      else if (stepNum === 3) nextBtn.innerText = 'Next: Shortcuts';
    }
    if (submitBtn) submitBtn.style.display = stepNum === 4 ? 'inline-flex' : 'none';
  }

  async nextInstallStep() {
    if (this.currentInstallStep === 1) {
      const archivePath = document.getElementById('installArchivePath').value.trim();
      if (!archivePath) {
        this.toast('Please select or upload a tarball archive file first', 'error');
        return;
      }
      if (!this.activeInspection) {
        await this.inspectArchive(archivePath);
        if (!this.activeInspection) return;
      }
      this.populateStep2FromInspection();
      this.showInstallStep(2);
    } else if (this.currentInstallStep === 2) {
      const slug = document.getElementById('installSlugName').value.trim();
      const dest = document.getElementById('installDestinationPath').value.trim();
      if (!slug) {
        this.toast('Please provide an app slug identifier', 'error');
        return;
      }
      if (!dest) {
        this.toast('Please provide an installation destination path', 'error');
        return;
      }
      this.populateStep3Candidates();
      this.showInstallStep(3);
    } else if (this.currentInstallStep === 3) {
      const customExec = document.getElementById('installExecCustomPath').value.trim();
      if (!this.selectedExecRelPath && !customExec) {
        this.toast('Please select or enter the main executable binary', 'error');
        return;
      }
      this.showInstallStep(4);
    }
  }

  prevInstallStep() {
    if (this.currentInstallStep > 1) {
      this.showInstallStep(this.currentInstallStep - 1);
    }
  }

  async handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
      await this.uploadFile(file);
    }
  }

  async uploadFile(file) {
    this.toast(`Uploading ${file.name}...`, 'info');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (res.ok && data.success) {
        document.getElementById('installArchivePath').value = data.saved_path;
        if (data.inspection) {
          this.activeInspection = data.inspection;
          this.renderInspectionPreview(data.inspection);
        }
        this.toast(`Loaded ${file.name}`, 'success');
      } else {
        this.toast(data.error || 'Upload failed', 'error');
      }
    } catch (e) {
      this.toast('Error uploading archive file', 'error');
    }
  }

  async inspectArchive(archivePath) {
    try {
      const res = await fetch('/api/apps/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archive_path: archivePath })
      });
      const data = await res.json();
      if (res.ok) {
        this.activeInspection = data;
        this.renderInspectionPreview(data);
      } else {
        this.toast(data.error || 'Failed to inspect archive', 'error');
      }
    } catch (e) {
      this.toast('Error inspecting archive file', 'error');
    }
  }

  renderInspectionPreview(info) {
    const box = document.getElementById('inspectionPreviewBox');
    box.style.display = 'block';
    document.getElementById('inspectArchiveSize').innerText = this.formatBytes(info.archive_size_bytes);
    document.getElementById('inspectFilesCount').innerText = `${info.total_files} files (${this.formatBytes(info.uncompressed_size_bytes)})`;
    document.getElementById('inspectWrapper').innerText = info.has_wrapper_folder ? `Yes (${info.wrapper_folder})` : 'None (flat archive)';
    document.getElementById('inspectExecCount').innerText = `${info.executables.length} detected`;
  }

  onArchiveSelectedFromBrowser(path) {
    app.inspectArchive(path);
  }

  populateStep2FromInspection() {
    if (!this.activeInspection) return;
    const info = this.activeInspection;
    if (!document.getElementById('installSlugName').value) {
      document.getElementById('installSlugName').value = info.guessed_name;
    }
    if (!document.getElementById('installDisplayName').value) {
      document.getElementById('installDisplayName').value = info.guessed_display_name;
    }
    if (!document.getElementById('installVersion').value) {
      document.getElementById('installVersion').value = info.guessed_version;
    }
    if (!document.getElementById('installDestinationPath').value) {
      document.getElementById('installDestinationPath').value = info.default_install_path;
    }
  }

  populateStep3Candidates() {
    if (!this.activeInspection) return;
    const execContainer = document.getElementById('executableCandidateList');
    const iconContainer = document.getElementById('iconCandidateList');

    const execs = this.activeInspection.executables || [];
    if (execs.length === 0) {
      execContainer.innerHTML = `<div style="font-size:0.775rem; color:var(--text-muted); padding:0.4rem;">No obvious binaries auto-detected. Specify path below:</div>`;
    } else {
      execContainer.innerHTML = execs.map((ex, idx) => `
        <div class="candidate-item ${idx === 0 ? 'selected' : ''}" onclick="app.selectExecCandidate('${this.escapeHtml(ex.path)}', this)">
          <div style="display:flex; align-items:center; gap:0.5rem; overflow:hidden;">
            <svg class="icon" style="width:14px;height:14px; color:var(--accent-primary);" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
            <span style="font-weight:600; font-size:0.8rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${this.escapeHtml(ex.path)}</span>
          </div>
          <span class="badge ${ex.is_exec_bit ? 'badge-emerald' : 'badge-slate'}" style="font-size:0.7rem;">${this.formatBytes(ex.size)}</span>
        </div>
      `).join('');
      if (execs.length > 0 && !this.selectedExecRelPath) {
        this.selectedExecRelPath = execs[0].path;
      }
    }

    const icons = this.activeInspection.icons || [];
    if (icons.length === 0) {
      iconContainer.innerHTML = `<div style="font-size:0.775rem; color:var(--text-muted); padding:0.4rem;">No icons auto-detected. You can select one below:</div>`;
    } else {
      iconContainer.innerHTML = icons.map((ic, idx) => `
        <div class="candidate-item ${idx === 0 ? 'selected' : ''}" onclick="app.selectIconCandidate('${this.escapeHtml(ic.path)}', this)">
          <div style="display:flex; align-items:center; gap:0.5rem; overflow:hidden;">
            <svg class="icon" style="width:14px;height:14px; color:var(--accent-secondary);" viewBox="0 0 24 24"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
            <span style="font-size:0.8rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${this.escapeHtml(ic.path)}</span>
          </div>
          <span class="badge badge-slate" style="font-size:0.7rem;">${this.formatBytes(ic.size)}</span>
        </div>
      `).join('');
      if (icons.length > 0 && !this.selectedIconRelPath) {
        this.selectedIconRelPath = icons[0].path;
      }
    }
  }

  selectExecCandidate(path, elem) {
    this.selectedExecRelPath = path;
    document.getElementById('installExecCustomPath').value = '';
    document.querySelectorAll('#executableCandidateList .candidate-item').forEach(el => el.classList.remove('selected'));
    elem.classList.add('selected');
  }

  selectIconCandidate(path, elem) {
    this.selectedIconRelPath = path;
    document.getElementById('installIconCustomPath').value = '';
    document.querySelectorAll('#iconCandidateList .candidate-item').forEach(el => el.classList.remove('selected'));
    elem.classList.add('selected');
  }

  async submitInstall() {
    const payload = {
      archive_path: document.getElementById('installArchivePath').value.trim(),
      name: document.getElementById('installSlugName').value.trim(),
      display_name: document.getElementById('installDisplayName').value.trim(),
      version: document.getElementById('installVersion').value.trim() || '1.0.0',
      description: document.getElementById('installDescription').value.trim(),
      category: 'Utility',
      install_path: document.getElementById('installDestinationPath').value.trim(),
      executable_rel_path: document.getElementById('installExecCustomPath').value.trim() || this.selectedExecRelPath,
      icon_rel_path: document.getElementById('installIconCustomPath').value.trim() || this.selectedIconRelPath,
      create_desktop: document.getElementById('installCreateDesktop').checked,
      create_bin_symlink: document.getElementById('installCreateSymlink').checked,
      flatten_wrapper: document.getElementById('installFlattenWrapper').checked,
      terminal: document.getElementById('installTerminal').checked,
      notes: document.getElementById('installNotes').value.trim()
    };

    const submitBtn = document.getElementById('wizardSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<div class="spinner"></div> Installing...`;

    try {
      const res = await fetch('/api/apps/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`${data.app.display_name} installed successfully!`, 'success');
        this.closeModal('installModal');
        await this.refreshApps();
        await this.refreshStats();
        await this.fetchDiscovered();
      } else {
        this.toast(data.error || 'Installation failed', 'error');
      }
    } catch (e) {
      this.toast('Error during installation: ' + e.message, 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Complete Installation`;
    }
  }

  // =========================================================================
  // Register Existing Application with Auto-Detection
  // =========================================================================
  openRegisterModal() {
    document.getElementById('regInstallPath').value = '';
    document.getElementById('regExecutablePath').value = '';
    document.getElementById('regName').value = '';
    document.getElementById('regDisplayName').value = '';
    document.getElementById('regVersion').value = '1.0.0';
    document.getElementById('regDescription').value = '';
    document.getElementById('regIconPath').value = '';
    document.getElementById('regCreateDesktop').checked = true;
    document.getElementById('regCreateSymlink').checked = true;
    document.getElementById('regExecutableCandidateList').innerHTML = '';
    this.openModal('registerModal');
  }

  async onRegisterDirChanged() {
    const dirPath = document.getElementById('regInstallPath').value.trim();
    if (!dirPath) return;

    this.toast('Auto-detecting binary, icon, and metadata...', 'info');

    try {
      const res = await fetch('/api/apps/auto-resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dirPath })
      });
      const data = await res.json();
      if (res.ok && !data.error) {
        if (data.display_name && !document.getElementById('regDisplayName').value) {
          document.getElementById('regDisplayName').value = data.display_name;
        }
        if (data.name && !document.getElementById('regName').value) {
          document.getElementById('regName').value = data.name;
        }
        if (data.version && document.getElementById('regVersion').value === '1.0.0') {
          document.getElementById('regVersion').value = data.version;
        }
        if (data.executable_path) {
          document.getElementById('regExecutablePath').value = data.executable_path;
        }
        if (data.icon_path) {
          document.getElementById('regIconPath').value = data.icon_path;
        }

        // Populate candidates dropdown list
        if (data.executables && data.executables.length > 0) {
          const list = document.getElementById('regExecutableCandidateList');
          list.innerHTML = data.executables.map((ex, idx) => `
            <div class="candidate-item ${idx === 0 ? 'selected' : ''}" onclick="document.getElementById('regExecutablePath').value='${this.escapeHtml(ex.full_path)}';">
              <span style="font-size:0.775rem; font-weight:600;">${this.escapeHtml(ex.path)}</span>
              <span class="badge ${ex.is_elf ? 'badge-emerald' : 'badge-slate'}" style="font-size:0.65rem;">${ex.is_elf ? 'ELF Binary' : 'Script'}</span>
            </div>
          `).join('');
        }

        this.toast(`Auto-detected ${data.display_name}!`, 'success');
      }
    } catch (e) {
      console.error('Auto-resolve error:', e);
    }
  }

  async submitRegister() {
    const payload = {
      name: document.getElementById('regName').value.trim(),
      display_name: document.getElementById('regDisplayName').value.trim(),
      install_path: document.getElementById('regInstallPath').value.trim(),
      executable_path: document.getElementById('regExecutablePath').value.trim(),
      version: document.getElementById('regVersion').value.trim() || '1.0.0',
      description: document.getElementById('regDescription').value.trim(),
      category: 'Utility',
      icon_path: document.getElementById('regIconPath').value.trim(),
      create_desktop: document.getElementById('regCreateDesktop').checked,
      create_bin_symlink: document.getElementById('regCreateSymlink').checked
    };

    if (!payload.install_path || !payload.executable_path || !payload.name) {
      this.toast('Please fill in install folder, executable path, and app name', 'error');
      return;
    }

    try {
      const res = await fetch('/api/apps/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`${data.app.display_name} registered successfully!`, 'success');
        this.closeModal('registerModal');
        await this.refreshApps();
        await this.refreshStats();
        await this.fetchDiscovered();
      } else {
        this.toast(data.error || 'Registration failed', 'error');
      }
    } catch (e) {
      this.toast('Error registering application', 'error');
    }
  }

  // =========================================================================
  // Update App Flow
  // =========================================================================
  openUpdateModal(appId) {
    const app = this.apps.find(a => a.id === appId);
    if (!app) return;
    this.activeApp = app;

    document.getElementById('updateAppNameHeader').innerText = app.display_name;
    document.getElementById('updateCurrentName').innerText = app.display_name;
    document.getElementById('updateCurrentVersion').innerText = `Current: v${app.version}`;
    document.getElementById('updateCurrentPath').innerText = app.install_path;
    document.getElementById('updateArchivePath').value = '';
    document.getElementById('updateNewVersion').value = '';
    document.getElementById('updateFlattenWrapper').checked = true;

    const sudoNotice = document.getElementById('updateSudoNotice');
    if (sudoNotice) {
      sudoNotice.style.display = app.needs_sudo ? 'flex' : 'none';
    }

    this.openModal('updateModal');
  }

  onUpdateArchiveSelected(path) {
    const match = path.match(/[-_.]v?(\d+(\.\d+)+)/);
    if (match) {
      document.getElementById('updateNewVersion').value = match[1];
    }
  }

  async submitUpdate() {
    if (!this.activeApp) return;
    const archivePath = document.getElementById('updateArchivePath').value.trim();
    if (!archivePath) {
      this.toast('Please specify the new tarball archive file', 'error');
      return;
    }

    const payload = {
      archive_path: archivePath,
      version: document.getElementById('updateNewVersion').value.trim() || null,
      flatten_wrapper: document.getElementById('updateFlattenWrapper').checked
    };

    try {
      const res = await fetch(`/api/apps/${this.activeApp.id}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`${data.app.display_name} updated to v${data.app.version} successfully!`, 'success');
        this.closeModal('updateModal');
        await this.refreshApps();
        await this.refreshStats();
      } else {
        this.toast(data.error || 'Update failed', 'error');
      }
    } catch (e) {
      this.toast('Error during update: ' + e.message, 'error');
    }
  }

  // =========================================================================
  // Uninstall App Flow
  // =========================================================================
  openUninstallModal(appId) {
    const app = this.apps.find(a => a.id === appId);
    if (!app) return;
    this.activeApp = app;

    document.getElementById('uninstallAppName').innerText = app.display_name;
    document.getElementById('uninstSizeStr').innerText = app.size_formatted;
    document.getElementById('uninstPathStr').innerText = this.shortenPath(app.install_path);
    document.getElementById('uninstDesktopStr').innerText = app.desktop_entry_path ? this.shortenPath(app.desktop_entry_path) : 'None';
    document.getElementById('uninstSymlinkStr').innerText = app.symlink_path ? this.shortenPath(app.symlink_path) : 'None';

    const sudoNotice = document.getElementById('uninstallSudoNotice');
    if (sudoNotice) {
      sudoNotice.style.display = app.needs_sudo ? 'flex' : 'none';
    }

    document.getElementById('uninstDeleteFiles').checked = true;
    document.getElementById('uninstDeleteDesktop').checked = Boolean(app.desktop_entry_path);
    document.getElementById('uninstDeleteSymlink').checked = Boolean(app.symlink_path);

    this.openModal('uninstallModal');
  }

  async submitUninstall() {
    if (!this.activeApp) return;

    const delFiles = document.getElementById('uninstDeleteFiles').checked;
    const delDesktop = document.getElementById('uninstDeleteDesktop').checked;
    const delSymlink = document.getElementById('uninstDeleteSymlink').checked;

    try {
      const res = await fetch(`/api/apps/${this.activeApp.id}?delete_files=${delFiles}&delete_desktop=${delDesktop}&delete_symlink=${delSymlink}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`Uninstalled ${data.app_name} cleanly! Freed ${this.formatBytes(data.bytes_freed)}`, 'success');
        this.closeModal('uninstallModal');
        await this.refreshApps();
        await this.refreshStats();
        await this.fetchDiscovered();
      } else {
        this.toast(data.error || 'Uninstall failed', 'error');
      }
    } catch (e) {
      this.toast('Error during uninstall: ' + e.message, 'error');
    }
  }

  // =========================================================================
  // App Details & Configuration Modal
  // =========================================================================
  openDetailsModal(appId) {
    const app = this.apps.find(a => a.id === appId);
    if (!app) return;
    this.activeApp = app;

    document.getElementById('editDisplayName').value = app.display_name;
    document.getElementById('editVersion').value = app.version;
    document.getElementById('editInstallPath').value = app.install_path;
    document.getElementById('editExecutablePath').value = app.executable_path;
    document.getElementById('editIconPath').value = app.icon_path || '';
    document.getElementById('editTerminal').checked = Boolean(app.terminal);
    document.getElementById('editNotes').value = app.notes || '';

    this.renderShortcutToggles(app);
    this.openModal('detailsModal');
  }

  renderShortcutToggles(app) {
    const desktopInfo = document.getElementById('editDesktopPathInfo');
    const desktopBtn = document.getElementById('toggleDesktopBtn');
    if (app.desktop_entry_path && app.desktop_exists) {
      desktopInfo.innerText = this.shortenPath(app.desktop_entry_path);
      desktopBtn.className = 'btn btn-sm btn-outline-danger';
      desktopBtn.innerText = 'Remove Shortcut';
    } else {
      desktopInfo.innerText = 'Not created';
      desktopBtn.className = 'btn btn-sm btn-primary';
      desktopBtn.innerText = 'Create Shortcut';
    }

    const symlinkInfo = document.getElementById('editSymlinkPathInfo');
    const symlinkBtn = document.getElementById('toggleSymlinkBtn');
    if (app.symlink_path && app.symlink_exists) {
      symlinkInfo.innerText = this.shortenPath(app.symlink_path);
      symlinkBtn.className = 'btn btn-sm btn-outline-danger';
      symlinkBtn.innerText = 'Remove Symlink';
    } else {
      symlinkInfo.innerText = 'Not created';
      symlinkBtn.className = 'btn btn-sm btn-primary';
      symlinkBtn.innerText = 'Create Symlink';
    }
  }

  async toggleShortcut(type) {
    if (!this.activeApp) return;
    const isCurrentlyActive = type === 'desktop' ? Boolean(this.activeApp.desktop_entry_path && this.activeApp.desktop_exists) : Boolean(this.activeApp.symlink_path && this.activeApp.symlink_exists);

    try {
      const res = await fetch(`/api/apps/${this.activeApp.id}/toggle-shortcut`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, enable: !isCurrentlyActive })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.activeApp = data.app;
        this.renderShortcutToggles(data.app);
        this.toast(`Shortcut updated`, 'success');
        await this.refreshApps();
        await this.refreshStats();
      }
    } catch (e) {
      this.toast('Error toggling shortcut', 'error');
    }
  }

  async saveAppEdit() {
    if (!this.activeApp) return;
    const payload = {
      display_name: document.getElementById('editDisplayName').value.trim(),
      version: document.getElementById('editVersion').value.trim(),
      category: 'Utility',
      executable_path: document.getElementById('editExecutablePath').value.trim(),
      icon_path: document.getElementById('editIconPath').value.trim(),
      terminal: document.getElementById('editTerminal').checked,
      notes: document.getElementById('editNotes').value.trim()
    };

    try {
      const res = await fetch(`/api/apps/${this.activeApp.id}/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast('Settings saved', 'success');
        this.closeModal('detailsModal');
        await this.refreshApps();
      }
    } catch (e) {
      this.toast('Error saving changes', 'error');
    }
  }

  openAppFolderFromEdit() {
    if (this.activeApp) {
      this.openFolder(this.activeApp.id);
    }
  }

  // =========================================================================
  // Visual File Browser Modal
  // =========================================================================
  openFileBrowser(mode, targetInputId, callback = null) {
    this.browserMode = mode || 'all';
    this.browserTargetInputId = targetInputId;
    this.browserOnSelectCallback = callback;
    this.browserSelectedItem = null;
    this.browserShowHidden = this.browserShowHidden !== undefined ? this.browserShowHidden : true;

    const hiddenToggle = document.getElementById('browserShowHidden');
    if (hiddenToggle) hiddenToggle.checked = this.browserShowHidden;

    document.getElementById('browserSelectedPreview').innerText = 'No item selected';

    let initialPath = '';
    const currentInputVal = document.getElementById(targetInputId)?.value;
    if (currentInputVal && currentInputVal.startsWith('/')) {
      initialPath = currentInputVal;
    }

    this.navigateToPath(initialPath);
    this.openModal('fileBrowserModal');
  }

  toggleBrowserHidden(checked) {
    this.browserShowHidden = Boolean(checked);
    this.navigateToPath(this.browserCurrentPath);
  }

  async navigateToPath(path) {
    try {
      const showHiddenParam = (this.browserShowHidden !== false) ? '1' : '0';
      const res = await fetch(`/api/browse?path=${encodeURIComponent(path || '')}&mode=${this.browserMode}&show_hidden=${showHiddenParam}`);
      if (!res.ok) return;
      const data = await res.json();
      this.browserCurrentPath = data.current_path;
      this.renderBrowser(data);
    } catch (e) {
      this.toast('Error browsing files', 'error');
    }
  }

  renderBrowser(data) {
    // Breadcrumbs
    const crumbsContainer = document.getElementById('browserBreadcrumbs');
    const parts = data.current_path.split('/').filter(Boolean);
    let cumulative = '';
    let crumbHtml = `<button class="crumb-btn" onclick="app.navigateToPath('/')">/</button>`;

    parts.forEach(part => {
      cumulative += '/' + part;
      const target = cumulative;
      crumbHtml += `<span style="color:var(--text-muted);">/</span><button class="crumb-btn" onclick="app.navigateToPath('${this.escapeHtml(target)}')">${this.escapeHtml(part)}</button>`;
    });
    crumbsContainer.innerHTML = crumbHtml;

    // Quick links
    const qlContainer = document.getElementById('browserQuickLinks');
    qlContainer.innerHTML = (data.quick_links || []).map(ql => `
      <button class="btn btn-sm btn-secondary" onclick="app.navigateToPath('${this.escapeHtml(ql.path)}')">
        ${this.escapeHtml(ql.name)}
      </button>
    `).join('');

    // List
    const listContainer = document.getElementById('browserItemsList');
    let itemsHtml = '';

    if (data.parent_path) {
      itemsHtml += `
        <div class="browser-row" onclick="app.navigateToPath('${this.escapeHtml(data.parent_path)}')">
          <div class="browser-item-left">
            <svg class="icon" style="color:var(--text-muted);" viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>
            <span style="font-weight:600;">.. (Parent Folder)</span>
          </div>
        </div>
      `;
    }

    if (!data.items || data.items.length === 0) {
      itemsHtml += `<div style="padding:1rem; text-align:center; color:var(--text-muted); font-size:0.8rem;">Directory is empty or contains no matching files</div>`;
    } else {
      data.items.forEach(item => {
        const icon = item.is_dir
          ? `<svg class="icon" style="color:var(--accent-secondary);" viewBox="0 0 24 24"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>`
          : item.is_archive
          ? `<svg class="icon" style="color:var(--accent-primary);" viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>`
          : `<svg class="icon" style="color:var(--text-muted);" viewBox="0 0 24 24"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/></svg>`;

        itemsHtml += `
          <div class="browser-row ${item.is_hidden ? 'is-hidden' : ''}" onclick="app.onBrowserItemClick('${this.escapeHtml(item.path)}', ${item.is_dir}, this)" ondblclick="app.onBrowserItemDblClick('${this.escapeHtml(item.path)}', ${item.is_dir})">
            <div class="browser-item-left">
              ${icon}
              <span class="browser-item-name">${this.escapeHtml(item.name)}</span>
            </div>
            <span style="color:var(--text-muted); font-size:0.75rem;">${item.size_formatted || ''}</span>
          </div>
        `;
      });
    }

    listContainer.innerHTML = itemsHtml;
  }

  onBrowserItemClick(path, isDir, elem) {
    this.browserSelectedItem = path;
    document.querySelectorAll('.browser-row').forEach(r => r.classList.remove('selected'));
    elem.classList.add('selected');
    document.getElementById('browserSelectedPreview').innerText = `Selected: ${path}`;
  }

  onBrowserItemDblClick(path, isDir) {
    if (isDir) {
      this.navigateToPath(path);
    } else {
      this.confirmBrowserSelection(path);
    }
  }

  confirmBrowserSelection(directPath = null) {
    const selected = directPath || this.browserSelectedItem || (this.browserMode === 'dir' ? this.browserCurrentPath : null);
    if (!selected) {
      this.toast('Please choose a file or folder', 'error');
      return;
    }

    if (this.browserTargetInputId) {
      const input = document.getElementById(this.browserTargetInputId);
      if (input) {
        input.value = selected;
        input.dispatchEvent(new Event('change'));
      }
    }

    if (this.browserOnSelectCallback && typeof this.browserOnSelectCallback === 'function') {
      this.browserOnSelectCallback(selected);
    }

    this.closeModal('fileBrowserModal');
  }

  // =========================================================================
  // Modal Utilities
  // =========================================================================
  openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('open');
  }

  closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('open');
  }

  closeAllModals() {
    document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.remove('open'));
  }

  // =========================================================================
  // Helper Functions & Notifications
  // =========================================================================
  toast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = `<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
    if (type === 'success') {
      icon = `<svg class="icon" style="color:var(--accent-emerald);" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
    } else if (type === 'error') {
      icon = `<svg class="icon" style="color:var(--accent-rose);" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
    }

    toast.innerHTML = `
      ${icon}
      <div style="flex:1; font-size:0.85rem; font-weight:500;">${this.escapeHtml(message)}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3500);
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  getMonogram(name) {
    if (!name) return 'A';
    const words = name.trim().split(/\s+/);
    if (words.length > 1) {
      return (words[0][0] + words[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }

  shortenPath(path) {
    if (!path) return '';
    const home = this.systemInfo.home || '';
    if (home && path.startsWith(home)) {
      return '~' + path.slice(home.length);
    }
    return path;
  }

  formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIdx = 0;
    while (size >= 1024 && unitIdx < units.length - 1) {
      size /= 1024;
      unitIdx++;
    }
    return `${size.toFixed(1)} ${units[unitIdx]}`;
  }

  // =========================================================================
  // Clean Master (Cache & Junk Cleaner)
  // =========================================================================
  async scanCleaner(force = false) {
    const rescanBtn = document.getElementById('cleanerRescanBtn');
    if (rescanBtn) {
      rescanBtn.disabled = true;
      rescanBtn.innerHTML = `<svg class="icon spin" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Scanning...`;
    }

    try {
      const res = await fetch('/api/cleaner/scan');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.cleanerData = data;

      const badge = document.getElementById('cleanerTotalBadge');
      if (badge) badge.textContent = data.total_size_formatted || '0 B';

      const heroSize = document.getElementById('cleanerHeroSize');
      if (heroSize) heroSize.textContent = data.total_size_formatted || '0 B';

      const heroDesc = document.getElementById('cleanerHeroDesc');
      if (heroDesc) {
        const count = data.targets.length;
        heroDesc.textContent = count > 0 
          ? `Found ${data.total_size_formatted} reclaimable caches and junk files across ${count} location${count === 1 ? '' : 's'}.`
          : 'All clean. No package manager or temporary caches found.';
      }

      if (this.selectedCleanerTargets.size === 0 || force) {
        this.selectedCleanerTargets.clear();
        for (const t of data.targets) {
          if (t.default_checked && t.safe_to_clean) {
            this.selectedCleanerTargets.add(t.id);
          }
        }
      }

      this.renderCleaner();
      this.updateCleanerSelectionMetrics();
    } catch (e) {
      console.error('Failed to scan caches:', e);
      this.toast('Failed to scan caches: ' + e.message, 'error');
    } finally {
      if (rescanBtn) {
        rescanBtn.disabled = false;
        rescanBtn.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg> Scan`;
      }
    }
  }

  updateCleanerSelectionMetrics() {
    if (!this.cleanerData || !this.cleanerData.targets) return;

    let selectedBytes = 0;
    for (const t of this.cleanerData.targets) {
      if (this.selectedCleanerTargets.has(t.id)) {
        selectedBytes += t.size_bytes || 0;
      }
    }

    const sizeStr = this.formatBytes(selectedBytes);
    const sizeSpan = document.getElementById('cleanSelectedSizeStr');
    if (sizeSpan) sizeSpan.textContent = sizeStr;

    const cleanBtn = document.getElementById('cleanSelectedBtn');
    if (cleanBtn) {
      cleanBtn.disabled = this.selectedCleanerTargets.size === 0 || this.isCleaning;
    }
  }

  toggleCleanerTarget(targetId) {
    if (this.selectedCleanerTargets.has(targetId)) {
      this.selectedCleanerTargets.delete(targetId);
    } else {
      this.selectedCleanerTargets.add(targetId);
    }
    this.updateCleanerSelectionMetrics();
  }

  toggleSelectAllCleaner() {
    if (!this.cleanerData || !this.cleanerData.targets) return;

    const allSelected = this.cleanerData.targets.every(t => this.selectedCleanerTargets.has(t.id));
    if (allSelected) {
      this.selectedCleanerTargets.clear();
    } else {
      for (const t of this.cleanerData.targets) {
        if (t.safe_to_clean) {
          this.selectedCleanerTargets.add(t.id);
        }
      }
    }
    this.renderCleaner();
    this.updateCleanerSelectionMetrics();
  }

  renderCleaner() {
    const container = document.getElementById('cleanerSections');
    if (!container) return;

    if (!this.cleanerData || !this.cleanerData.targets || this.cleanerData.targets.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding:3rem 1rem;">
          <svg class="empty-icon" style="color:var(--accent-emerald);" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <h3 class="empty-title">System is Clean</h3>
          <p class="empty-desc">No package manager caches or junk files found on your system.</p>
        </div>
      `;
      return;
    }

    const categories = [
      { id: 'package_managers', title: 'Package Managers & AUR', icon: '<path d="m16.5 9.4-9-5.19M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>' },
      { id: 'developer', title: 'Developer Tools & Runtimes', icon: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>' },
      { id: 'system', title: 'Desktop & Temporary Junk', icon: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>' }
    ];

    let html = '';
    for (const cat of categories) {
      const items = this.cleanerData.targets.filter(t => t.category === cat.id);
      if (items.length === 0) continue;

      let catBytes = items.reduce((acc, t) => acc + (t.size_bytes || 0), 0);

      html += `
        <div class="cleaner-category-section">
          <div class="cleaner-category-header">
            <div class="cleaner-category-header-title">
              <svg class="icon" viewBox="0 0 24 24" style="color:var(--accent-emerald); width:16px; height:16px;">
                ${cat.icon}
              </svg>
              <span>${cat.title}</span>
            </div>
            <span class="badge badge-slate">${this.formatBytes(catBytes)}</span>
          </div>
          <div class="cleaner-category-items">
      `;

      for (const item of items) {
        const isChecked = this.selectedCleanerTargets.has(item.id);
        const rootBadge = item.needs_sudo 
          ? `<span class="badge" style="background:rgba(245, 158, 11, 0.12); color:#fbbf24; border:1px solid rgba(245, 158, 11, 0.3);">Root / Sudo</span>`
          : `<span class="badge" style="background:var(--accent-emerald-bg); color:var(--accent-emerald);">Safe to clean</span>`;

        html += `
          <div class="cleaner-target-item">
            <div class="cleaner-target-info">
              <input type="checkbox" class="cleaner-target-checkbox" id="check_${item.id}"
                ${isChecked ? 'checked' : ''}
                onchange="app.toggleCleanerTarget('${item.id}')"
              >
              <div class="cleaner-target-meta">
                <div class="cleaner-target-title-row">
                  <label for="check_${item.id}" class="cleaner-target-name" style="cursor:pointer;">${this.escapeHtml(item.name)}</label>
                  ${rootBadge}
                </div>
                <div class="cleaner-target-path">${this.escapeHtml(item.path)}</div>
                <div class="cleaner-target-desc">${this.escapeHtml(item.description)}</div>
              </div>
            </div>
            <div class="cleaner-target-stats">
              <div class="cleaner-target-numbers">
                <div class="cleaner-size-badge">${item.size_formatted}</div>
                <div class="cleaner-files-count">${item.file_count.toLocaleString()} files</div>
              </div>
              <button class="btn btn-sm btn-secondary" onclick="app.cleanSingleTarget('${item.id}')" title="Clean only this cache">
                Clean
              </button>
            </div>
          </div>
        `;
      }

      html += `
          </div>
        </div>
      `;
    }

    container.innerHTML = html;
  }

  showSudoCommandModal(sudoTargets, userFreedNotice = '') {
    const desc = document.getElementById('sudoCommandDesc');
    const codeEl = document.getElementById('sudoCommandCode');
    const noticeEl = document.getElementById('sudoNonRootCleanNotice');

    const names = sudoTargets.map(t => t.name).join(', ');
    if (desc) {
      desc.innerHTML = `Administrator privileges are required to clean <strong>${this.escapeHtml(names)}</strong>. Run this command in your terminal:`;
    }

    const commands = sudoTargets.map(t => t.sudo_command || `sudo rm -rf '${t.path}'/*`);
    const uniqueCommands = Array.from(new Set(commands));
    const commandText = uniqueCommands.join(' && ');

    if (codeEl) {
      codeEl.textContent = commandText;
    }

    if (noticeEl) {
      if (userFreedNotice) {
        noticeEl.style.display = 'block';
        noticeEl.innerHTML = `✓ User-level caches cleaned successfully (freed ${this.escapeHtml(userFreedNotice)}).`;
      } else {
        noticeEl.style.display = 'none';
        noticeEl.innerHTML = '';
      }
    }

    this.openModal('sudoCommandModal');
  }

  copySudoCommand() {
    const codeEl = document.getElementById('sudoCommandCode');
    const text = codeEl ? codeEl.textContent : '';
    if (text) {
      navigator.clipboard.writeText(text).then(() => {
        this.toast('Command copied to clipboard!', 'success');
      }).catch(() => {
        this.toast('Failed to copy. Please select and copy manually.', 'error');
      });
    }
  }

  async completeSudoCommandClean() {
    this.closeModal('sudoCommandModal');
    this.toast('Refreshing cache scan...', 'info');
    await this.scanCleaner(true);
  }

  async cleanSelectedCaches() {
    if (this.selectedCleanerTargets.size === 0) {
      this.toast('No caches selected to clean.', 'info');
      return;
    }

    const targetsToClean = Array.from(this.selectedCleanerTargets);
    const allTargets = this.cleanerData?.targets || [];
    const sudoTargets = allTargets.filter(t => targetsToClean.includes(t.id) && t.needs_sudo);
    const userTargets = allTargets.filter(t => targetsToClean.includes(t.id) && !t.needs_sudo);

    let userFreedStr = '';
    if (userTargets.length > 0) {
      const btn = document.getElementById('cleanSelectedBtn');
      this.isCleaning = true;
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<svg class="icon spin" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Cleaning...`;
      }

      try {
        const res = await fetch('/api/cleaner/clean', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ targets: userTargets.map(t => t.id) })
        });
        if (res.ok) {
          const data = await res.json();
          userFreedStr = data.freed_formatted || '0 B';
        }
      } catch (e) {
        console.error('Failed to clean user targets:', e);
      } finally {
        this.isCleaning = false;
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `
            <svg class="icon" viewBox="0 0 24 24"><path d="m19 11-8-8-8.6 8.6a2 2 0 0 0 0 2.8l5.2 5.2c.8.8 2 .8 2.8 0L19 11Z"/><path d="m5 2 5 5"/><path d="M2 5l5 5"/><path d="m22 20-2 2-4-4 2-2 4 4Z"/></svg>
            Clean Selected (<span id="cleanSelectedSizeStr">0 B</span>)
          `;
        }
      }
    }

    if (sudoTargets.length > 0) {
      this.showSudoCommandModal(sudoTargets, userFreedStr);
    } else {
      if (userFreedStr) {
        this.toast(`Clean complete. Freed ${userFreedStr} of disk space!`, 'success');
      }
      await this.scanCleaner(true);
      this.updateCleanerSelectionMetrics();
    }
  }

  async cleanSingleTarget(targetId) {
    const target = (this.cleanerData?.targets || []).find(t => t.id === targetId);
    if (target && target.needs_sudo) {
      this.showSudoCommandModal([target]);
      return;
    }

    try {
      this.toast('Cleaning cache...', 'info');
      const res = await fetch('/api/cleaner/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets: [targetId] })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const freedStr = data.freed_formatted || '0 B';
      this.toast(`Cleaned ${freedStr}`, 'success');
      await this.scanCleaner(true);
    } catch (e) {
      console.error('Single clean failed:', e);
      this.toast('Clean failed: ' + e.message, 'error');
    }
  }
}

// Global initialization
const app = new TarGzApp();
