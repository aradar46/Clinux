/**
 * Clinux 1.0 - Vintage 1990s Linux Utility JavaScript
 * Pure Vanilla JS with Zero External Dependencies
 */

class ClinuxApp {
  constructor() {
    this.apps = [];
    this.discoveredApps = [];
    this.stats = {};
    this.systemInfo = {};
    this.currentTab = 'dashboard';
    this.currentSort = 'name_asc';
    this.searchQuery = '';

    // Selected Navigation Index for Keyboard Navigation
    this.selectedNavIdx = 0;
    this.navItemKeys = ['dashboard', 'security', 'cleaner', 'storage', 'services', 'all', 'ai', 'dotfiles'];

    // Security Audit State
    this.securityData = null;

    // CRT Effect
    this.crtEnabled = true;

    // Active App in Focus
    this.activeApp = null;
    this.clientId = 'client_' + Math.random().toString(36).substring(2, 10);

    // Cleaner State
    this.cleanerData = null;
    this.selectedCleanerTargets = new Set();
    this.isCleaning = false;

    // AI State
    this.aiSubTab = 'skills';
    this.aiSkills = [];
    this.aiCategories = [];
    this.aiStorage = { models: [], workspaces: [] };
    this.selectedAgentTargets = ['claude', 'agy'];
    this.aiFilterCategory = 'all';
    this.aiSkillSearchQuery = '';

    // File Browser
    this.browserMode = 'all';
    this.browserTargetInputId = null;
    this.browserOnSelectCallback = null;
    this.browserCurrentPath = '';
    this.browserSelectedItem = null;

    this.init();
  }

  async init() {
    this.setupTheme();
    this.setupCRT();
    this.setupEventListeners();
    this.startHeartbeat();
    await this.fetchSystemInfo();
    await this.fetchOptions();
    await this.refreshApps();
    await this.fetchDiscovered();
    await this.refreshDashboardStats();
    if (this.options && this.options.behavior && !this.options.behavior.start_dashboard) {
      const firstTab = (this.options.tabs.find(t => t.visible) || {}).id || 'dashboard';
      this.setTab(firstTab);
    } else {
      this.setTab('dashboard');
    }
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
    setInterval(sendPing, 3000);

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') sendPing();
    });

    const handleClose = () => {
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/shutdown', JSON.stringify({ client_id: this.clientId }));
      }
    };
    window.addEventListener('beforeunload', handleClose);
    window.addEventListener('pagehide', handleClose);
  }

  // =========================================================================
  // Theme & CRT Effect Settings
  // =========================================================================
  setupTheme() {
    const savedTheme = localStorage.getItem('clinux_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
  }

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('clinux_theme', next);
    this.toast(`Theme set to ${next}`, 'info');
  }

  setupCRT() {
    const savedCRT = localStorage.getItem('clinux_crt');
    this.crtEnabled = savedCRT !== 'off';
    if (this.crtEnabled) {
      document.body.classList.add('crt-mode');
    } else {
      document.body.classList.remove('crt-mode');
    }
    this.updateCRTButton();
  }

  toggleCRT() {
    this.crtEnabled = !this.crtEnabled;
    if (this.crtEnabled) {
      document.body.classList.add('crt-mode');
      localStorage.setItem('clinux_crt', 'on');
    } else {
      document.body.classList.remove('crt-mode');
      localStorage.setItem('clinux_crt', 'off');
    }
    this.updateCRTButton();
    this.toast(`CRT Effect: ${this.crtEnabled ? 'ON' : 'OFF'}`, 'info');
  }

  updateCRTButton() {
    const btn = document.getElementById('crtToggleBtn');
    if (btn) btn.innerText = `CRT: ${this.crtEnabled ? 'ON' : 'OFF'}`;
  }

  // =========================================================================
  // Event Listeners & Keyboard Navigation
  // =========================================================================
  setupEventListeners() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.trim();
        if (this.currentTab === 'all' || this.currentTab === 'ignored' || this.currentTab === 'discovered') {
          this.renderApps();
        }
      });
    }

    // Keyboard Shortcuts (Arrow keys, Esc, /, ?, Ctrl+K, q)
    window.addEventListener('keydown', (e) => {
      if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
        if (e.key === 'Escape') {
          document.activeElement.blur();
        }
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.navigateTree(1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this.navigateTree(-1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        this.setTab(this.navItemKeys[this.selectedNavIdx]);
      } else if (e.key === 'Escape') {
        this.closeAllModals();
      } else if (e.key === '/') {
        e.preventDefault();
        searchInput?.focus();
      } else if (e.key === '?') {
        e.preventDefault();
        this.openHelpModal();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        this.openCommandPalette();
      } else if (e.key === 'q') {
        e.preventDefault();
        this.closeAllModals();
      }
    });

    document.querySelectorAll('.modal-backdrop').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this.closeModal(modal.id);
      });
    });
  }

  navigateTree(dir) {
    this.selectedNavIdx = (this.selectedNavIdx + dir + this.navItemKeys.length) % this.navItemKeys.length;
    const targetTab = this.navItemKeys[this.selectedNavIdx];
    this.highlightNavItem(targetTab);
  }

  highlightNavItem(tab) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    let elId = 'nav' + tab.charAt(0).toUpperCase() + tab.slice(1);
    if (tab === 'all') elId = 'navApps';

    const targetEl = document.getElementById(elId);
    if (targetEl) targetEl.classList.add('active');
  }

  // =========================================================================
  // API Calls & Data Fetching
  // =========================================================================
  async fetchSystemInfo() {
    try {
      const res = await fetch('/api/system-info');
      if (res.ok) {
        this.systemInfo = await res.json();
        const u = document.getElementById('statusUser');
        if (u) u.innerText = this.systemInfo.user || 'user';
      }
    } catch (e) {
      console.error('Failed system info:', e);
    }
  }

  async refreshDashboardStats() {
    try {
      const statsRes = await fetch('/api/stats');
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        const disk = statsData.stats?.disk;
        if (disk) {
          const healthEl = document.getElementById('dashHealthTitle');
          if (healthEl && disk.health_display_str) {
            healthEl.innerText = disk.health_display_str;
          }
          const diskEl = document.getElementById('dashDiskUsageStr');
          if (diskEl) {
            diskEl.innerText = `${disk.used_formatted} / ${disk.total_formatted} (${disk.usage_percent}%)`;
          }
        }
      }

      const storageRes = await fetch('/api/ai/storage');
      if (storageRes.ok) {
        const sData = await storageRes.json();
        const aiEl = document.getElementById('dashAIModelSize');
        if (aiEl) aiEl.innerText = sData.total_size_formatted || '0 GB';
      }

      const cleanRes = await fetch('/api/cleaner/scan');
      if (cleanRes.ok) {
        const cData = await cleanRes.json();
        const clEl = document.getElementById('dashCleanerSize');
        if (clEl) clEl.innerText = cData.total_size_formatted || '0 GB';
      }
    } catch (e) {
      console.error('Failed dashboard stats:', e);
    }
  }

  async refreshApps() {
    try {
      const res = await fetch('/api/apps');
      if (res.ok) {
        const data = await res.json();
        this.apps = data.apps || [];
        const activeCount = this.apps.filter(a => !a.ignored).length;
        const countAll = document.getElementById('countAllApps');
        const appsBadge = document.getElementById('appsNavBadge');
        if (countAll) countAll.innerText = activeCount;
        if (appsBadge) appsBadge.innerText = activeCount;
        this.updateIgnoredCount();
        if (this.currentTab === 'all' || this.currentTab === 'ignored') {
          this.renderApps();
        }
      }
    } catch (e) {
      this.toast('Error fetching apps', 'error');
    }
  }

  async refreshAll() {
    this.toast('Refreshing system info...', 'info');
    await this.refreshApps();
    await this.fetchDiscovered();
    await this.refreshDashboardStats();
    this.toast('System refresh complete', 'success');
  }

  async fetchDiscovered() {
    try {
      const res = await fetch('/api/discovered');
      if (res.ok) {
        const data = await res.json();
        this.discoveredApps = data.discovered || [];
        this.renderDiscoveredBanner();
        if (this.currentTab === 'discovered') {
          this.renderApps();
        }
      }
    } catch (e) {
      console.error('Discovery fetch error:', e);
    }
  }

  renderDiscoveredBanner() {
    const banner = document.getElementById('discoveredBanner');
    const navItem = document.getElementById('navDiscovered');
    const countPill = document.getElementById('discoveredCountPill');
    const navBadge = document.getElementById('pillDiscoveredCount');

    const available = this.getActiveDiscovered();

    if (available.length > 0) {
      if (banner) banner.style.display = 'block';
      if (navItem) navItem.style.display = 'flex';
      if (countPill) countPill.innerText = available.length;
      if (navBadge) navBadge.innerText = available.length;
    } else {
      if (banner) banner.style.display = 'none';
      if (navItem) navItem.style.display = 'none';
      if (this.currentTab === 'discovered') this.setTab('all');
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

  // =========================================================================
  // View Navigation Handling
  // =========================================================================
  setTab(tab) {
    this.currentTab = tab;
    this.highlightNavItem(tab);

    const views = {
      dashboard: document.getElementById('dashboardView'),
      cleaner: document.getElementById('cleanerView'),
      apps: document.getElementById('appsView'),
      ai: document.getElementById('aiView'),
      dotfiles: document.getElementById('dotfilesView'),
      options: document.getElementById('optionsView'),
      empty: document.getElementById('emptyState')
    };

    Object.values(views).forEach(v => {
      if (v) v.style.display = 'none';
    });

    this.renderSidebarModules();

    if (tab === 'dashboard') {
      if (views.dashboard) views.dashboard.style.display = 'flex';
      this.refreshDashboardStats();
    } else if (tab === 'cleaner') {
      if (views.cleaner) views.cleaner.style.display = 'flex';
      this.scanCleaner(false);
    } else if (tab === 'options') {
      if (views.options) views.options.style.display = 'flex';
      this.populateOptionsForm();
    } else if (tab === 'storage') {
      if (views.ai) views.ai.style.display = 'flex';
      this.setAISubTab('storage');
    } else if (tab === 'ai') {
      if (views.ai) views.ai.style.display = 'flex';
      this.loadAIData();
    } else if (tab === 'dotfiles') {
      if (views.dotfiles) views.dotfiles.style.display = 'flex';
      this.fetchDotfilesStatus();
    } else {
      // Portable Apps (all, ignored, discovered)
      if (views.apps) views.apps.style.display = 'flex';
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
  // Render Applications Grid (Retro Panel Cards)
  // =========================================================================
  renderApps() {
    const grid = document.getElementById('appsGrid');
    const emptyState = document.getElementById('emptyState');
    const list = this.getFilteredApps();

    if (!list || list.length === 0) {
      if (grid) grid.innerHTML = '';
      if (emptyState) emptyState.style.display = 'block';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';

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
    return `
      <div class="retro-panel" id="discovered-card-${idx}">
        <div class="retro-panel-title">DISCOVERED APP #${idx + 1}</div>
        <div style="font-size:14px; font-weight:bold; color:var(--c-terminal-green-bright); margin-bottom:4px;">
          ${this.escapeHtml(item.display_name)}
        </div>
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:6px;">
          Version: ${this.escapeHtml(item.version || '1.0')} | Size: ${item.size_formatted}
        </div>
        <div class="terminal-box" style="margin-bottom:8px; max-height:50px;">
          LOC: ${this.escapeHtml(this.shortenPath(item.install_path || item.archive_path))}
        </div>
        <div style="display:flex; gap:6px;">
          <button class="retro-btn retro-btn-green" onclick="app.addSingleDiscovered(${idx})">Import</button>
          <button class="retro-btn" onclick="app.reviewDiscovered(${idx})">Review</button>
          <button class="retro-btn" onclick="app.ignoreDiscovered(${idx})">Ignore</button>
        </div>
      </div>
    `;
  }

  renderAppCard(app) {
    const statusDot = app.status_color === 'red' ? '⚠ FAIL' : '● OK';

    return `
      <div class="retro-panel" id="app-card-${app.id}">
        <div class="retro-panel-title">${this.escapeHtml(app.display_name).toUpperCase()}</div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-weight:bold; color:var(--c-terminal-green-bright);">${this.escapeHtml(app.display_name)}</span>
          <span style="color:${app.status_color === 'red' ? 'var(--c-danger-red)' : 'var(--c-terminal-green)'}; font-size:11px;">${statusDot}</span>
        </div>
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:6px;">
          v${this.escapeHtml(app.version || '1.0.0')} | ${app.size_formatted}
        </div>
        <div class="terminal-box" style="margin-bottom:8px; font-size:11px; max-height:60px;">
          BIN: ${this.escapeHtml(this.shortenPath(app.executable_path))}<br>
          DIR: ${this.escapeHtml(this.shortenPath(app.install_path))}
        </div>
        <div style="display:flex; gap:4px; flex-wrap:wrap;">
          <button class="retro-btn retro-btn-green" onclick="app.launchApp(${app.id})">Launch</button>
          <button class="retro-btn" onclick="app.openFolder(${app.id})">Folder</button>
          <button class="retro-btn" onclick="app.openUpdateModal(${app.id})">Update</button>
          <button class="retro-btn" onclick="app.openDetailsModal(${app.id})">Config</button>
          <button class="retro-btn retro-btn-danger" onclick="app.openUninstallModal(${app.id})">Remove</button>
        </div>
      </div>
    `;
  }

  // =========================================================================
  // Discovered Actions
  // =========================================================================
  async addSingleDiscovered(index) {
    const item = this.discoveredApps[index];
    if (!item) return;

    this.toast(`Importing ${item.display_name}...`, 'info');
    try {
      const res = await fetch('/api/discovered/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`Imported ${data.app.display_name}!`, 'success');
        await this.refreshApps();
        await this.fetchDiscovered();
      } else {
        this.toast(data.error || 'Import failed', 'error');
      }
    } catch (e) {
      this.toast('Error importing application: ' + e.message, 'error');
    }
  }

  async addAllDiscovered() {
    const available = this.getActiveDiscovered();
    if (available.length === 0) return;

    this.toast(`Importing ${available.length} applications...`, 'info');
    let added = 0;
    for (const item of available) {
      try {
        const res = await fetch('/api/discovered/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(item)
        });
        if (res.ok) added++;
      } catch (e) {}
    }

    this.toast(`Successfully imported ${added} applications!`, 'success');
    await this.refreshApps();
    await this.fetchDiscovered();
    this.setTab('all');
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
  // Install & Register Modals
  // =========================================================================
  openInstallWizard() {
    document.getElementById('installArchivePath').value = '';
    document.getElementById('inspectionPreviewBox').style.display = 'none';
    document.getElementById('installDisplayName').value = '';
    document.getElementById('installSlugName').value = '';
    document.getElementById('installVersion').value = '';
    document.getElementById('installDestinationPath').value = '';
    document.getElementById('installDescription').value = '';

    this.openModal('installModal');
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
        const box = document.getElementById('inspectionPreviewBox');
        if (box) box.style.display = 'block';
        document.getElementById('inspectArchiveSize').innerText = this.formatBytes(data.archive_size_bytes);
        document.getElementById('inspectFilesCount').innerText = `${data.total_files} files`;
        document.getElementById('inspectWrapper').innerText = data.has_wrapper_folder ? 'Yes' : 'None';
        document.getElementById('inspectExecCount').innerText = `${data.executables.length} detected`;

        if (!document.getElementById('installSlugName').value) document.getElementById('installSlugName').value = data.guessed_name;
        if (!document.getElementById('installDisplayName').value) document.getElementById('installDisplayName').value = data.guessed_display_name;
        if (!document.getElementById('installVersion').value) document.getElementById('installVersion').value = data.guessed_version;
        if (!document.getElementById('installDestinationPath').value) document.getElementById('installDestinationPath').value = data.default_install_path;
      }
    } catch (e) {
      this.toast('Error inspecting archive', 'error');
    }
  }

  onArchiveSelectedFromBrowser(path) {
    app.inspectArchive(path);
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
      create_desktop: document.getElementById('installCreateDesktop').checked,
      create_bin_symlink: document.getElementById('installCreateSymlink').checked,
      flatten_wrapper: document.getElementById('installFlattenWrapper').checked,
      terminal: document.getElementById('installTerminal').checked
    };

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
      } else {
        this.toast(data.error || 'Installation failed', 'error');
      }
    } catch (e) {
      this.toast('Error during installation', 'error');
    }
  }

  openRegisterModal() {
    document.getElementById('regInstallPath').value = '';
    document.getElementById('regExecutablePath').value = '';
    document.getElementById('regName').value = '';
    document.getElementById('regDisplayName').value = '';
    document.getElementById('regVersion').value = '1.0.0';
    document.getElementById('regDescription').value = '';
    document.getElementById('regIconPath').value = '';
    this.openModal('registerModal');
  }

  async onRegisterDirChanged() {
    const dirPath = document.getElementById('regInstallPath').value.trim();
    if (!dirPath) return;

    try {
      const res = await fetch('/api/apps/auto-resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dirPath })
      });
      const data = await res.json();
      if (res.ok && !data.error) {
        if (data.display_name) document.getElementById('regDisplayName').value = data.display_name;
        if (data.name) document.getElementById('regName').value = data.name;
        if (data.version) document.getElementById('regVersion').value = data.version;
        if (data.executable_path) document.getElementById('regExecutablePath').value = data.executable_path;
        if (data.icon_path) document.getElementById('regIconPath').value = data.icon_path;
        this.toast(`Auto-detected ${data.display_name}`, 'success');
      }
    } catch (e) {}
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
      } else {
        this.toast(data.error || 'Registration failed', 'error');
      }
    } catch (e) {
      this.toast('Error registering application', 'error');
    }
  }

  // =========================================================================
  // Update & Uninstall
  // =========================================================================
  openUpdateModal(appId) {
    const app = this.apps.find(a => a.id === appId);
    if (!app) return;
    this.activeApp = app;

    document.getElementById('updateAppNameHeader').innerText = app.display_name;
    document.getElementById('updateCurrentName').innerText = app.display_name;
    document.getElementById('updateCurrentVersion').innerText = `v${app.version}`;
    document.getElementById('updateCurrentPath').innerText = app.install_path;
    document.getElementById('updateArchivePath').value = '';
    document.getElementById('updateNewVersion').value = '';

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
      this.toast('Please specify archive path', 'error');
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
        this.toast(`${data.app.display_name} updated successfully!`, 'success');
        this.closeModal('updateModal');
        await this.refreshApps();
      } else {
        this.toast(data.error || 'Update failed', 'error');
      }
    } catch (e) {
      this.toast('Error during update', 'error');
    }
  }

  openUninstallModal(appId) {
    const app = this.apps.find(a => a.id === appId);
    if (!app) return;
    this.activeApp = app;

    document.getElementById('uninstallAppName').innerText = app.display_name;
    document.getElementById('uninstSizeStr').innerText = app.size_formatted;
    document.getElementById('uninstPathStr').innerText = this.shortenPath(app.install_path);
    document.getElementById('uninstDesktopStr').innerText = app.desktop_entry_path ? this.shortenPath(app.desktop_entry_path) : 'None';
    document.getElementById('uninstSymlinkStr').innerText = app.symlink_path ? this.shortenPath(app.symlink_path) : 'None';

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
        this.toast(`Uninstalled ${data.app_name}!`, 'success');
        this.closeModal('uninstallModal');
        await this.refreshApps();
      } else {
        this.toast(data.error || 'Uninstall failed', 'error');
      }
    } catch (e) {
      this.toast('Error during uninstall', 'error');
    }
  }

  // =========================================================================
  // Config Modal
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

    this.openModal('detailsModal');
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

  async toggleShortcut(type) {
    if (!this.activeApp) return;
    const isCurrentlyActive = type === 'desktop' ? Boolean(this.activeApp.desktop_entry_path) : Boolean(this.activeApp.symlink_path);

    try {
      const res = await fetch(`/api/apps/${this.activeApp.id}/toggle-shortcut`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, enable: !isCurrentlyActive })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.activeApp = data.app;
        this.toast('Shortcut updated', 'success');
        await this.refreshApps();
      }
    } catch (e) {
      this.toast('Error toggling shortcut', 'error');
    }
  }

  // =========================================================================
  // Clean Master Views
  // =========================================================================
  async scanCleaner(force = false) {
    const rescanBtn = document.getElementById('cleanerRescanBtn');
    if (rescanBtn) rescanBtn.innerText = 'Scanning...';

    try {
      const res = await fetch('/api/cleaner/scan');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.cleanerData = data;

      const badge = document.getElementById('cleanerTotalBadge');
      if (badge) badge.textContent = data.total_size_formatted || '0 B';

      const heroDesc = document.getElementById('cleanerHeroDesc');
      if (heroDesc) {
        heroDesc.textContent = `Found ${data.total_size_formatted} reclaimable junk across ${data.targets.length} targets.`;
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
      console.error('Scan error:', e);
    } finally {
      if (rescanBtn) rescanBtn.innerText = '[ R ] RE-SCAN';
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
    const sizeSpan = document.getElementById('cleanSelectedSizeStr');
    if (sizeSpan) sizeSpan.textContent = this.formatBytes(selectedBytes);
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
        if (t.safe_to_clean) this.selectedCleanerTargets.add(t.id);
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
        <div class="terminal-box" style="padding:16px; text-align:center;">
          <div style="color:var(--c-terminal-green-bright); font-size:14px; font-weight:bold;">NO CACHES FOUND</div>
          <div style="color:var(--text-muted);">System is completely clean.</div>
        </div>
      `;
      return;
    }

    const totalFormatted = this.cleanerData.total_size_formatted || '0 B';

    container.innerHTML = `
      <div class="retro-panel" style="margin-top:0;">
        <div class="retro-panel-title">FOUND RECLAIMABLE CACHES</div>
        <table class="retro-table">
          <thead>
            <tr>
              <th style="width:24px;">[X]</th>
              <th>CACHE NAME</th>
              <th>CATEGORY</th>
              <th>SIZE</th>
              <th>FILES</th>
              <th>LOCATION</th>
              <th style="width:80px;">ACTION</th>
            </tr>
          </thead>
          <tbody>
            ${this.cleanerData.targets.map(t => {
              const checked = this.selectedCleanerTargets.has(t.id);
              return `
                <tr class="${checked ? 'selected' : ''}">
                  <td><input type="checkbox" ${checked ? 'checked' : ''} onchange="app.toggleCleanerTarget('${t.id}')"></td>
                  <td><strong style="color:var(--c-terminal-green-bright);">${this.escapeHtml(t.name)}</strong></td>
                  <td>${this.escapeHtml(t.category)}</td>
                  <td><strong style="color:var(--c-warning-yellow);">${t.size_formatted}</strong></td>
                  <td>${t.file_count}</td>
                  <td style="font-size:11px; color:var(--text-muted);">${this.escapeHtml(this.shortenPath(t.path))}</td>
                  <td><button class="retro-btn" onclick="app.cleanSingleTarget('${t.id}')">Clean</button></td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
        <div style="margin-top:10px; padding-top:8px; border-top:1px dashed var(--c-shadow); display:flex; justify-content:space-between; align-items:center;">
          <div><strong style="color:var(--c-warning-yellow);">TOTAL RECLAIMABLE: ${totalFormatted}</strong></div>
          <div style="display:flex; gap:8px;">
            <button class="retro-btn retro-btn-green" onclick="app.cleanSelectedCaches()">[ C ] CLEAN SELECTED</button>
            <button class="retro-btn" onclick="app.scanCleaner(true)">[ V ] PREVIEW / RESCAN</button>
            <button class="retro-btn" onclick="app.setTab('dashboard')">[ Q ] CANCEL</button>
          </div>
        </div>
      </div>
    `;
  }

  async cleanSelectedCaches() {
    if (this.selectedCleanerTargets.size === 0) {
      this.toast('No caches selected.', 'info');
      return;
    }

    const targetsToClean = Array.from(this.selectedCleanerTargets);
    const allTargets = this.cleanerData?.targets || [];
    const sudoTargets = allTargets.filter(t => targetsToClean.includes(t.id) && t.needs_sudo);
    const userTargets = allTargets.filter(t => targetsToClean.includes(t.id) && !t.needs_sudo);

    let userFreedStr = '';
    if (userTargets.length > 0) {
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
      } catch (e) {}
    }

    if (sudoTargets.length > 0) {
      this.showSudoCommandModal(sudoTargets, userFreedStr);
    } else {
      if (userFreedStr) this.toast(`Clean complete! Freed ${userFreedStr}`, 'success');
      await this.scanCleaner(true);
    }
  }

  async cleanSingleTarget(targetId) {
    const target = (this.cleanerData?.targets || []).find(t => t.id === targetId);
    if (target && target.needs_sudo) {
      this.showSudoCommandModal([target]);
      return;
    }

    try {
      const res = await fetch('/api/cleaner/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets: [targetId] })
      });
      if (res.ok) {
        const data = await res.json();
        this.toast(`Cleaned ${data.freed_formatted || '0 B'}`, 'success');
        await this.scanCleaner(true);
      }
    } catch (e) {
      this.toast('Clean failed', 'error');
    }
  }

  showSudoCommandModal(sudoTargets, userFreedNotice = '') {
    const desc = document.getElementById('sudoCommandDesc');
    const codeEl = document.getElementById('sudoCommandCode');
    const noticeEl = document.getElementById('sudoNonRootCleanNotice');

    const names = sudoTargets.map(t => t.name || t.id).join(', ');
    if (desc) desc.innerText = `Root privileges required to clean: ${names}`;

    const commands = sudoTargets.map(t => t.sudo_command || `sudo rm -rf '${t.path}'/*`);
    if (codeEl) codeEl.textContent = Array.from(new Set(commands)).join(' && ');

    if (noticeEl) {
      if (userFreedNotice) {
        noticeEl.style.display = 'block';
        noticeEl.innerText = `User caches cleaned successfully (freed ${userFreedNotice}).`;
      } else {
        noticeEl.style.display = 'none';
      }
    }
    this.openModal('sudoCommandModal');
  }

  copySudoCommand() {
    const codeEl = document.getElementById('sudoCommandCode');
    if (codeEl && codeEl.textContent) {
      navigator.clipboard.writeText(codeEl.textContent).then(() => {
        this.toast('Command copied to clipboard!', 'success');
      });
    }
  }

  async completeSudoCommandClean() {
    this.closeModal('sudoCommandModal');
    await this.scanCleaner(true);
  }

  // =========================================================================
  // AI Tooling & Skills Manager
  // =========================================================================
  setAISubTab(subTab) {
    this.aiSubTab = subTab;
    const tabSkills = document.getElementById('aiTabSkills');
    const tabStorage = document.getElementById('aiTabStorage');
    const secSkills = document.getElementById('aiSkillsSection');
    const secStorage = document.getElementById('aiStorageSection');

    if (tabSkills) tabSkills.classList.toggle('pressed', subTab === 'skills');
    if (tabStorage) tabStorage.classList.toggle('pressed', subTab === 'storage');

    if (subTab === 'skills') {
      if (secSkills) secSkills.style.display = 'block';
      if (secStorage) secStorage.style.display = 'none';
      if (this.aiSkills.length === 0) this.fetchAISkills();
    } else {
      if (secSkills) secSkills.style.display = 'none';
      if (secStorage) secStorage.style.display = 'block';
      this.fetchAIStorage(false);
    }
  }

  async loadAIData() {
    await Promise.all([this.fetchAISkills(), this.fetchAIStorage(false)]);
  }

  async rescanAI() {
    this.toast('Scanning AI skills and storage...', 'info');
    await Promise.all([this.fetchAISkills(), this.fetchAIStorage(true)]);
    this.toast('AI scan refreshed', 'success');
  }

  async fetchAISkills() {
    try {
      const res = await fetch('/api/ai/skills');
      if (res.ok) {
        const data = await res.json();
        this.aiSkills = data.skills || [];
        this.aiCategories = data.categories || [];
        const rootInput = document.getElementById('aiSkillsRoot');
        if (rootInput && document.activeElement !== rootInput) rootInput.value = data.skills_root || '';

        const badge = document.getElementById('aiSkillsBadge');
        const countPill = document.getElementById('aiSkillsCount');
        const activeCount = this.aiSkills.filter(s => s.active).length;
        if (badge) badge.textContent = `${activeCount}/${this.aiSkills.length}`;
        if (countPill) countPill.textContent = `${activeCount}/${this.aiSkills.length}`;

        this.populateAICategories();
        this.renderAISkills();
      }
    } catch (e) {}
  }

  populateAICategories() {
    const select = document.getElementById('aiCategoryFilter');
    if (!select) return;
    let html = '<option value="all">All Categories</option>';
    this.aiCategories.forEach(cat => {
      html += `<option value="${this.escapeHtml(cat)}">${this.escapeHtml(cat)}</option>`;
    });
    select.innerHTML = html;
  }

  async saveAISkillsRoot() {
    const skillsRoot = document.getElementById('aiSkillsRoot')?.value.trim();
    if (!skillsRoot) return this.toast('Enter a skills-library path', 'error');
    try {
      const res = await fetch('/api/ai/skills/source', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skills_root: skillsRoot })
      });
      const data = await res.json();
      if (!res.ok) return this.toast(data.error || 'Could not use that path', 'error');
      this.toast('Skills library configured', 'success');
      await this.fetchAISkills();
    } catch (e) { this.toast('Could not configure skills library', 'error'); }
  }

  filterSkills(query) {
    this.aiSkillSearchQuery = (query || '').toLowerCase().trim();
    this.renderAISkills();
  }

  filterSkillCategory(cat) {
    this.aiFilterCategory = cat || 'all';
    this.renderAISkills();
  }

  getFilteredSkills() {
    return this.aiSkills.filter(s => {
      if (this.aiFilterCategory !== 'all' && s.category !== this.aiFilterCategory) return false;
      if (this.aiSkillSearchQuery) {
        const text = `${s.name} ${s.category} ${s.description}`.toLowerCase();
        if (!text.includes(this.aiSkillSearchQuery)) return false;
      }
      return true;
    });
  }

  renderAISkills() {
    const container = document.getElementById('aiSkillsGrid');
    if (!container) return;

    const filtered = this.getFilteredSkills();

    if (filtered.length === 0) {
      container.innerHTML = `<div class="terminal-box" style="padding:16px;">No skills match filter.</div>`;
      return;
    }

    const groups = {};
    filtered.forEach(s => {
      const cat = (s.category || 'GENERAL').toUpperCase();
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(s);
    });

    let html = '';
    for (const [catName, skillList] of Object.entries(groups)) {
      html += `
        <div class="retro-panel" style="margin-top:0; margin-bottom:10px;">
          <div class="retro-panel-title">${this.escapeHtml(catName)}</div>
          <div class="ai-skill-card-grid">
            ${skillList.map(skill => {
              const description = skill.description || 'No description provided.';
              return `
                <div class="ai-skill-card ${skill.active ? 'active' : ''}" role="button" tabindex="0"
                     onclick="if(event.target.tagName !== 'BUTTON') app.toggleSkill('${this.escapeHtml(skill.key)}', ${!skill.active})">
                  <strong class="ai-skill-card-name" title="${this.escapeHtml(description)}">${this.escapeHtml(skill.display_name || skill.name)}</strong>
                  <span class="ai-skill-tooltip" role="tooltip">${this.escapeHtml(description)}</span>
                  <div class="ai-skill-card-footer">
                    <span class="ai-skill-card-status">${skill.active ? '● ACTIVE' : '○ INACTIVE'}</span>
                    <button class="retro-btn ${skill.active ? '' : 'retro-btn-green'}" onclick="event.stopPropagation(); app.toggleSkill('${this.escapeHtml(skill.key)}', ${!skill.active})">
                      ${skill.active ? 'DISABLE' : 'ENABLE'}
                    </button>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    container.innerHTML = html;
  }

  async toggleSkill(skillKey, active) {
    try {
      const res = await fetch('/api/ai/skills/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: skillKey, active })
      });
      if (res.ok) {
        this.toast(`${active ? 'Activated' : 'Deactivated'} ${skillKey}`, 'success');
        await this.fetchAISkills();
      }
    } catch (e) {
      this.toast('Toggle failed', 'error');
    }
  }

  async bulkToggleCurrentCategory(active) {
    const cat = this.aiFilterCategory;

    if (cat === 'all') {
      for (const c of this.aiCategories) {
        await fetch('/api/ai/skills/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category: c, active })
        });
      }
    } else {
      await fetch('/api/ai/skills/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: cat, active })
      });
    }
    this.toast(`Updated skills`, 'success');
    await this.fetchAISkills();
  }

  async fetchAIStorage(force) {
    try {
      const res = await fetch('/api/ai/storage');
      if (res.ok) {
        const data = await res.json();
        this.aiStorage = data;
        const total = data.total_size_formatted || '0 B';
        const badge = document.getElementById('aiStorageTotal');
        if (badge) badge.textContent = total;
        this.renderAIStorage();
      }
    } catch (e) {}
  }

  renderAIStorage() {
    const modelsList = document.getElementById('aiModelsList');
    const workspacesList = document.getElementById('aiWorkspacesList');
    const models = this.aiStorage.models || [];
    const workspaces = this.aiStorage.workspaces || [];

    if (modelsList) {
      if (models.length === 0) {
        modelsList.innerHTML = `<div style="padding:8px; color:var(--text-muted);">No local models detected.</div>`;
      } else {
        modelsList.innerHTML = `
          <table class="retro-table">
            <thead>
              <tr><th>SOURCE</th><th>MODEL NAME</th><th>SIZE</th><th>ACTION</th></tr>
            </thead>
            <tbody>
              ${models.map(m => `
                <tr>
                  <td><strong>${this.escapeHtml(m.source)}</strong></td>
                  <td>${this.escapeHtml(m.name)}</td>
                  <td><strong style="color:var(--c-warning-yellow);">${m.size_formatted}</strong></td>
                  <td><button class="retro-btn retro-btn-danger" onclick="app.deleteAIModel('${this.escapeHtml(m.id)}', '${this.escapeHtml(m.name)}')">Delete</button></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }
    }

    if (workspacesList) {
      if (workspaces.length === 0) {
        workspacesList.innerHTML = `<div style="padding:8px; color:var(--text-muted);">No workspaces detected.</div>`;
      } else {
        workspacesList.innerHTML = `
          <table class="retro-table">
            <thead>
              <tr><th>TARGET</th><th>SIZE</th><th>FILES</th><th>ACTION</th></tr>
            </thead>
            <tbody>
              ${workspaces.map(w => `
                <tr>
                  <td><strong>${this.escapeHtml(w.name)}</strong></td>
                  <td><strong style="color:var(--c-warning-yellow);">${w.size_formatted}</strong></td>
                  <td>${w.file_count}</td>
                  <td><button class="retro-btn" onclick="app.cleanAIWorkspace('${this.escapeHtml(w.id)}', '${this.escapeHtml(w.name)}')">Clean Logs</button></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }
    }
  }

  async deleteAIModel(modelId, modelName) {
    if (!confirm(`Delete model "${modelName}"?`)) return;
    try {
      const res = await fetch('/api/ai/storage/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId })
      });
      if (res.ok) {
        this.toast(`Deleted ${modelName}`, 'success');
        await this.fetchAIStorage(true);
      }
    } catch (e) {}
  }

  async cleanAIWorkspace(workspaceId, workspaceName) {
    if (!confirm(`Clean logs for "${workspaceName}"?`)) return;
    try {
      const res = await fetch('/api/ai/storage/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace_id: workspaceId })
      });
      if (res.ok) {
        this.toast(`Cleaned ${workspaceName}`, 'success');
        await this.fetchAIStorage(true);
      }
    } catch (e) {}
  }

  // =========================================================================
  // Dotfiles Manager
  // =========================================================================
  async fetchDotfilesStatus(showToast = false) {
    try {
      const res = await fetch('/api/dotfiles/status');
      if (res.ok) {
        const data = await res.json();
        this.dotfilesData = data;
        this.renderDotfiles();
        if (showToast) this.toast('Dotfiles refreshed', 'success');
      }
    } catch (e) {}
  }

  renderDotfiles() {
    const d = this.dotfilesData;
    if (!d) return;

    const heroTitle = document.getElementById('dotfilesHeroTitle');
    const branch = document.getElementById('dotfilesBranch');
    const gitState = document.getElementById('dotfilesGitState');
    const pkgsList = document.getElementById('dotfilesPackagesList');

    if (heroTitle) heroTitle.textContent = d.repo_path || '~/.dotfiles';
    if (d.git && d.git.is_git) {
      if (branch) branch.textContent = d.git.branch || 'main';
      if (gitState) {
        gitState.textContent = d.git.clean ? 'clean' : `${d.git.modified_files} modified`;
        gitState.style.color = d.git.clean ? 'var(--c-terminal-green-bright)' : 'var(--c-warning-yellow)';
      }
    }

    if (pkgsList && d.packages) {
      pkgsList.innerHTML = d.packages.map(p => {
        const name = typeof p === 'object' ? p.name : p;
        const stowed = typeof p === 'object' ? p.stowed : false;
        return `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 6px; background:var(--c-near-black); border:1px solid var(--c-shadow);">
            <span>${this.escapeHtml(name)} <small style="color:${stowed ? 'var(--c-terminal-green-bright)' : 'var(--text-muted)'};">[${stowed ? 'STOWED' : 'NOT STOWED'}]</small></span>
            <button class="retro-btn" onclick="app.runDotfilesCommand('${stowed ? 'unstow' : 'stow'}', null, '${this.escapeHtml(name)}')">
              ${stowed ? 'Unstow' : 'Stow'}
            </button>
          </div>
        `;
      }).join('');
    }
  }

  async runDotfilesCommand(command, message = null, packageName = null) {
    const consoleElem = document.getElementById('dotfilesOutputConsole');
    const badgeElem = document.getElementById('dotfilesOutputBadge');

    if (badgeElem) badgeElem.textContent = 'Running...';
    if (consoleElem) consoleElem.textContent = `--> dotfiles ${command}...\n`;

    try {
      const res = await fetch('/api/dotfiles/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, message, package: packageName })
      });
      const data = await res.json();
      if (consoleElem) consoleElem.textContent = data.output || (data.success ? 'Completed.' : 'Failed.');
      if (badgeElem) badgeElem.textContent = data.success ? 'Success' : 'Failed';
      await this.fetchDotfilesStatus(false);
    } catch (e) {
      if (consoleElem) consoleElem.textContent = `Error: ${e.message}`;
    }
  }

  saveDotfiles() {
    const input = document.getElementById('dotfilesCommitMsg');
    const msg = input ? input.value.trim() : '';
    if (!msg) {
      this.toast('Enter commit message', 'info');
      return;
    }
    this.runDotfilesCommand('save', msg);
    if (input) input.value = '';
  }

  // =========================================================================
  // Self Update
  // =========================================================================
  async triggerDirectUpdate() {
    this.toast('Updating Clinux from GitHub...', 'info');
    try {
      const res = await fetch('/api/self-update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast('Updated! Reloading...', 'success');
        setTimeout(() => window.location.reload(), 1000);
      } else {
        this.toast('Update failed', 'error');
      }
    } catch (e) {
      this.toast('Update failed', 'error');
    }
  }

  // =========================================================================
  // File Browser Modal
  // =========================================================================
  openFileBrowser(mode, targetInputId, callback = null) {
    this.browserMode = mode || 'all';
    this.browserTargetInputId = targetInputId;
    this.browserOnSelectCallback = callback;
    this.browserSelectedItem = null;

    const val = document.getElementById(targetInputId)?.value;
    this.navigateToPath(val && val.startsWith('/') ? val : '');
    this.openModal('fileBrowserModal');
  }

  async navigateToPath(path) {
    try {
      const res = await fetch(`/api/browse?path=${encodeURIComponent(path || '')}&mode=${this.browserMode}`);
      if (res.ok) {
        const data = await res.json();
        this.browserCurrentPath = data.current_path;
        this.renderBrowser(data);
      }
    } catch (e) {}
  }

  renderBrowser(data) {
    const crumbs = document.getElementById('browserBreadcrumbs');
    if (crumbs) crumbs.innerText = data.current_path;

    const list = document.getElementById('browserItemsList');
    if (!list) return;

    let itemsHtml = '';
    if (data.parent_path) {
      itemsHtml += `<div style="cursor:pointer; padding:2px;" onclick="app.navigateToPath('${this.escapeHtml(data.parent_path)}')">[..] Parent Directory</div>`;
    }

    (data.items || []).forEach(item => {
      itemsHtml += `
        <div style="cursor:pointer; padding:2px;" onclick="app.onBrowserItemClick('${this.escapeHtml(item.path)}', this)" ondblclick="app.onBrowserItemDblClick('${this.escapeHtml(item.path)}', ${item.is_dir})">
          ${item.is_dir ? '[DIR]' : '[FILE]'} ${this.escapeHtml(item.name)}
        </div>
      `;
    });
    list.innerHTML = itemsHtml;
  }

  onBrowserItemClick(path, elem) {
    this.browserSelectedItem = path;
    const prev = document.getElementById('browserSelectedPreview');
    if (prev) prev.innerText = `Selected: ${path}`;
  }

  onBrowserItemDblClick(path, isDir) {
    if (isDir) this.navigateToPath(path);
    else this.confirmBrowserSelection(path);
  }

  confirmBrowserSelection(directPath = null) {
    const selected = directPath || this.browserSelectedItem || this.browserCurrentPath;
    if (this.browserTargetInputId) {
      const input = document.getElementById(this.browserTargetInputId);
      if (input) {
        input.value = selected;
        input.dispatchEvent(new Event('change'));
      }
    }
    if (this.browserOnSelectCallback) this.browserOnSelectCallback(selected);
    this.closeModal('fileBrowserModal');
  }

  // =========================================================================
  // Modal & Help Dialog Utilities
  // =========================================================================
  async fetchOptions() {
    try {
      const res = await fetch('/api/options');
      const data = await res.json();
      if (data.options) {
        this.options = data.options;
        if (this.options.tabs) {
          this.options.tabs = this.options.tabs.filter(t => t.id !== 'projects');
        }
        this.applyOptionsToUI();
      }
    } catch (e) {
      console.error('Failed to fetch options:', e);
    }
  }

  applyOptionsToUI() {
    if (!this.options) return;

    // Appearance
    const appr = this.options.appearance || {};
    const theme = appr.theme || 'classic-green';
    const font = appr.font || 'bitmap';
    const crt = appr.crt_effects !== false;

    if (theme === 'classic-green') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }

    document.body.className = '';
    document.body.classList.add(`font-${font}`);
    if (crt) document.body.classList.add('crt-mode');

    const crtBtn = document.getElementById('crtToggleBtn');
    if (crtBtn) crtBtn.textContent = crt ? 'CRT: ON' : 'CRT: OFF';

    this.renderSidebarModules();
    this.populateOptionsForm();
  }

  renderSidebarModules() {
    const container = document.getElementById('sidebarModulesTree');
    if (!container || !this.options || !this.options.tabs) return;

    const visibleTabs = this.options.tabs.filter(t => t.visible && t.id !== 'projects');
    let html = '';

    visibleTabs.forEach(t => {
      const activeClass = this.currentTab === t.id ? 'active' : '';

      let badgeHtml = '';
      if (t.id === 'cleaner') {
        badgeHtml = `<span class="nav-badge nav-badge-warn" id="cleanerTotalBadge">0 B</span>`;
      } else if (t.id === 'apps') {
        badgeHtml = `<span class="nav-badge" id="appsNavBadge">${this.apps ? this.apps.length : 0}</span>`;
      } else if (t.id === 'ai') {
        badgeHtml = `<span class="nav-badge" id="aiSkillsBadge">${this.aiSkills ? this.aiSkills.length : 0}</span>`;
      } else if (t.id === 'dotfiles') {
        badgeHtml = `<span class="nav-badge nav-badge-warn" id="dotfilesBadge" style="display:none;">dirty</span>`;
      }

      html += `
        <div class="nav-item ${activeClass}" id="nav_${t.id}" onclick="app.setTab('${t.id}')">
          <span>${t.name}</span>
          ${badgeHtml}
        </div>
      `;
    });

    container.innerHTML = html;
  }

  populateOptionsForm() {
    if (!this.options) return;

    // Tabs List
    this.renderOptionsTabsList();

    // Appearance
    const appr = this.options.appearance || {};
    const themeSel = document.getElementById('optThemeSelect');
    if (themeSel) themeSel.value = appr.theme || 'classic-green';

    const fontSel = document.getElementById('optFontSelect');
    if (fontSel) fontSel.value = appr.font || 'bitmap';

    const crtChk = document.getElementById('optCrtEffects');
    if (crtChk) crtChk.checked = appr.crt_effects !== false;

    const animChk = document.getElementById('optAnimations');
    if (animChk) animChk.checked = !!appr.animations;

    // Behavior
    const beh = this.options.behavior || {};
    const confirmChk = document.getElementById('optConfirmDestructive');
    if (confirmChk) confirmChk.checked = beh.confirm_destructive !== false;

    const cmdsChk = document.getElementById('optShowCommands');
    if (cmdsChk) cmdsChk.checked = beh.show_commands !== false;

    const bkpChk = document.getElementById('optCreateBackups');
    if (bkpChk) bkpChk.checked = beh.create_backups !== false;

    const startDashChk = document.getElementById('optStartDashboard');
    if (startDashChk) startDashChk.checked = beh.start_dashboard !== false;

    // Cleaner
    const cln = (this.options.modules && this.options.modules.cleaner) || {};
    const pkgs = cln.package_managers || {};
    ['pacman', 'yay', 'flatpak', 'apt', 'dnf'].forEach(pm => {
      const el = document.getElementById(`optCleaner${pm.charAt(0).toUpperCase() + pm.slice(1)}`);
      if (el) el.checked = pkgs[pm] !== false;
    });

    const devs = cln.developer_caches || {};
    ['pip', 'uv', 'npm', 'cargo', 'conda', 'r'].forEach(d => {
      const el = document.getElementById(`optCleaner${d.charAt(0).toUpperCase() + d.slice(1)}`);
      if (el) el.checked = devs[d] !== false;
    });

    const reqConfirm = document.getElementById('optCleanerReqConfirm');
    if (reqConfirm) reqConfirm.checked = cln.require_confirmation !== false;

    const showSpace = document.getElementById('optCleanerShowSpace');
    if (showSpace) showSpace.checked = cln.show_reclaimable_space !== false;
  }

  renderOptionsTabsList() {
    const list = document.getElementById('optionsTabsList');
    if (!list || !this.options || !this.options.tabs) return;

    const visibleCount = this.options.tabs.filter(t => t.visible).length;
    const totalCount = this.options.tabs.length;

    const visEl = document.getElementById('optionsVisibleCount');
    if (visEl) visEl.textContent = visibleCount;

    const totEl = document.getElementById('optionsTotalCount');
    if (totEl) totEl.textContent = totalCount;

    let html = '';
    this.options.tabs.forEach((t, idx) => {
      const checked = t.visible ? 'checked' : '';
      html += `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:4px; border-bottom:1px dashed var(--c-shadow);">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="color:var(--text-muted);">☰</span>
            <input type="checkbox" id="chk_tab_${t.id}" ${checked} onchange="app.toggleOptionTab('${t.id}', this.checked)">
            <label for="chk_tab_${t.id}" style="font-weight:bold; cursor:pointer;">${t.name}</label>
          </div>
          <div style="display:flex; gap:4px;">
            <button class="win-btn" onclick="app.moveOptionTab(${idx}, -1)" ${idx === 0 ? 'disabled' : ''} title="Move Up">↑</button>
            <button class="win-btn" onclick="app.moveOptionTab(${idx}, 1)" ${idx === totalCount - 1 ? 'disabled' : ''} title="Move Down">↓</button>
          </div>
        </div>
      `;
    });

    list.innerHTML = html;
  }

  moveOptionTab(idx, direction) {
    if (!this.options || !this.options.tabs) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= this.options.tabs.length) return;

    const temp = this.options.tabs[idx];
    this.options.tabs[idx] = this.options.tabs[newIdx];
    this.options.tabs[newIdx] = temp;

    this.renderOptionsTabsList();
  }

  toggleOptionTab(tabId, visible) {
    if (!this.options || !this.options.tabs) return;
    const tab = this.options.tabs.find(t => t.id === tabId);
    if (tab) {
      tab.visible = visible;
      this.renderOptionsTabsList();
    }
  }

  async applyOptions() {
    if (!this.options) return;

    // Appearance
    this.options.appearance = {
      theme: document.getElementById('optThemeSelect').value,
      font: document.getElementById('optFontSelect').value,
      crt_effects: document.getElementById('optCrtEffects').checked,
      animations: document.getElementById('optAnimations').checked
    };

    // Behavior
    this.options.behavior = {
      confirm_destructive: document.getElementById('optConfirmDestructive').checked,
      show_commands: document.getElementById('optShowCommands').checked,
      create_backups: document.getElementById('optCreateBackups').checked,
      start_dashboard: document.getElementById('optStartDashboard').checked
    };

    // Cleaner
    this.options.modules = this.options.modules || {};
    this.options.modules.cleaner = {
      package_managers: {
        pacman: document.getElementById('optCleanerPacman').checked,
        yay: document.getElementById('optCleanerYay').checked,
        flatpak: document.getElementById('optCleanerFlatpak').checked,
        apt: document.getElementById('optCleanerApt').checked,
        dnf: document.getElementById('optCleanerDnf').checked
      },
      developer_caches: {
        pip: document.getElementById('optCleanerPip').checked,
        uv: document.getElementById('optCleanerUv').checked,
        npm: document.getElementById('optCleanerNpm').checked,
        cargo: document.getElementById('optCleanerCargo').checked,
        conda: document.getElementById('optCleanerConda').checked,
        r: document.getElementById('optCleanerR').checked
      },
      require_confirmation: document.getElementById('optCleanerReqConfirm').checked,
      show_reclaimable_space: document.getElementById('optCleanerShowSpace').checked
    };
    if (this.options.modules) {
      delete this.options.modules.security;
    }

    try {
      const res = await fetch('/api/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ options: this.options })
      });
      const data = await res.json();
      if (data.success) {
        this.options = data.options;
        this.applyOptionsToUI();
        this.toast('✓ Options saved and applied successfully!', 'info');
      }
    } catch (e) {
      this.toast('Failed to save options', 'error');
    }
  }

  async resetOptions() {
    if (!confirm('Reset all Clinux options to default values?')) return;
    try {
      const res = await fetch('/api/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' })
      });
      const data = await res.json();
      if (data.success) {
        this.options = data.options;
        this.applyOptionsToUI();
        this.toast('✓ Options reset to default values', 'info');
      }
    } catch (e) {
      this.toast('Failed to reset options', 'error');
    }
  }

  openAboutModal() {
    this.openModal('aboutModal');
  }

  quitApp() {
    if (confirm('Shut down Clinux web server and exit?')) {
      fetch('/api/shutdown', { method: 'POST' }).catch(() => {});
      this.toast('Server shut down. You can close this tab.', 'info');
      setTimeout(() => window.close(), 1000);
    }
  }

  openHelpModal() {
    this.openModal('helpModal');
  }

  openCommandPalette() {
    const cmd = prompt('CLINUX COMMAND PALETTE:\n1: Dashboard\n2: Cleaner\n3: Portable Apps\n4: AI & Skills\n5: Dotfiles\n6: Options\nq: Exit', '1');
    if (cmd === '1') this.setTab('dashboard');
    else if (cmd === '2') this.setTab('cleaner');
    else if (cmd === '3') this.setTab('all');
    else if (cmd === '4') this.setTab('ai');
    else if (cmd === '5') this.setTab('dotfiles');
    else if (cmd === '6') this.setTab('options');
  }

  closeWindow() {
    if (confirm('Quit Clinux Utility?')) {
      window.close();
    }
  }

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

  toast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>[${type.toUpperCase()}]</span> <span>${this.escapeHtml(message)}</span>`;

    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  shortenPath(path) {
    if (!path) return '';
    const home = this.systemInfo.home || '';
    if (home && path.startsWith(home)) return '~' + path.slice(home.length);
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
}

// Global initialization
const app = new ClinuxApp();
