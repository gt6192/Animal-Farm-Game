(() => {
  const sectionRules = [
    { key: 'settings', label: 'Game settings', icon: '⚙️', titles: ['GLOBAL SETTINGS'] },
    { key: 'animals', label: 'Animals', icon: '🐾', titles: ['NEW ANIMAL', 'MARKET & TIMING'] },
    { key: 'feed', label: 'Feed', icon: '🌾', titles: ['NEW FEED', 'FEED MARKET'] },
    { key: 'land', label: 'Land', icon: '🌱', titles: ['LAND'] },
    { key: 'progression', label: 'Levels & XP', icon: '⭐', titles: ['LEVELS & XP', 'MANUAL XP'] },
    { key: 'upgrades', label: 'Upgrades', icon: '🏗️', titles: ['INVENTORY & TRANSPORT LEVELS'] },
    { key: 'fishery', label: 'Fishery', icon: '🐟', titles: ['FISHERY CATALOG'] },
    { key: 'vendors', label: 'Vendor map', icon: '🗺️', titles: ['VENDOR MAP'] },
    { key: 'processing', label: 'Processing', icon: '⚙️', titles: ['PROCESSING'] },
    { key: 'players', label: 'Players', icon: '👩‍🌾', titles: ['FARMERS'] }
  ];
  const shell = document.querySelector('.shell');
  const header = shell?.querySelector('.topbar');
  const sections = [...(shell?.querySelectorAll(':scope > section.panel') || [])];
  if (!shell || !header || !sections.length) return;

  const workspace = document.createElement('div');
  workspace.className = 'admin-workspace';
  const sidebar = document.createElement('aside');
  sidebar.className = 'admin-sidebar';
  sidebar.innerHTML = '<div class="admin-sidebar-title"><span>🌿</span><div><small>FARM CONTROL</small><strong>Admin menu</strong></div></div>';
  const navigation = document.createElement('nav');
  navigation.setAttribute('aria-label', 'Admin sections');
  const content = document.createElement('div');
  content.className = 'admin-content';
  const overview = document.createElement('section');
  overview.className = 'admin-overview';
  overview.dataset.adminSection = 'overview';
  const count = title => sections.find(section => section.querySelector('.eyebrow')?.textContent.trim() === title)?.querySelectorAll('tbody tr, .admin-grid > form').length || 0;
  overview.innerHTML = `<div class="admin-section-heading"><p>ADMIN OVERVIEW</p><h2>Farm economy at a glance</h2><span>Choose a workspace from the menu to edit its rules.</span></div><div class="admin-overview-grid"><article><span>🐾</span><strong>${count('MARKET & TIMING')}</strong><small>animal species</small></article><article><span>🌾</span><strong>${count('FEED MARKET')}</strong><small>feed products</small></article><article><span>⭐</span><strong>${count('LEVELS & XP')}</strong><small>player levels</small></article><article><span>🏗️</span><strong>${count('INVENTORY & TRANSPORT LEVELS')}</strong><small>upgrade entries</small></article></div>`;
  content.appendChild(overview);

  sections.forEach(section => {
    const title = section.querySelector('.eyebrow')?.textContent.trim();
    const rule = sectionRules.find(item => item.titles.includes(title));
    if (!rule) return;
    section.dataset.adminSection = rule.key;
    content.appendChild(section);
  });

  const items = [{ key: 'overview', label: 'Overview', icon: '📊' }, ...sectionRules];
  const activate = key => {
    const valid = items.some(item => item.key === key) ? key : 'overview';
    content.querySelectorAll('[data-admin-section]').forEach(section => { section.hidden = section.dataset.adminSection !== valid; });
    navigation.querySelectorAll('button').forEach(button => button.setAttribute('aria-current', button.dataset.section === valid ? 'page' : 'false'));
    localStorage.setItem('animalFarmAdminSection', valid);
    history.replaceState(history.state, '', `#${valid}`);
    document.querySelector('.admin-content')?.scrollTo({ top: 0, behavior: 'auto' });
  };
  items.forEach(item => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.section = item.key;
    button.innerHTML = `<span>${item.icon}</span><b>${item.label}</b>`;
    button.addEventListener('click', () => activate(item.key));
    navigation.appendChild(button);
  });
  sidebar.appendChild(navigation);
  const alert = shell.querySelector(':scope > .game-alert');
  if (alert) content.prepend(alert);
  workspace.append(sidebar, content);
  header.after(workspace);
  const requested = location.hash.slice(1) || localStorage.getItem('animalFarmAdminSection') || 'overview';
  activate(requested);
  window.addEventListener('hashchange', () => activate(location.hash.slice(1)));

  const processing = content.querySelector('[data-admin-section="processing"]');
  if (processing) {
    const groups = {
      buildings: { label: 'Buildings', icon: '🏭', headings: ['New building', 'Edit buildings'] },
      levels: { label: 'Slot levels', icon: '⬆️', headings: ['Building slot upgrades'] },
      products: { label: 'Products', icon: '📦', headings: ['New processed product', 'Edit processed products'] },
      recipes: { label: 'Recipes', icon: '🧾', headings: ['New recipe', 'Existing recipes'] },
      audit: { label: 'Job audit', icon: '📋', headings: ['Recent processing jobs'] }
    };
    const headings = [...processing.querySelectorAll(':scope > h3')];
    if (headings.length) {
      const tabbar = document.createElement('nav');
      tabbar.className = 'processing-admin-tabs';
      tabbar.setAttribute('aria-label', 'Processing administration');
      const panelHost = document.createElement('div');
      panelHost.className = 'processing-admin-panels';
      const panels = {};
      Object.entries(groups).forEach(([key, group]) => {
        const button = document.createElement('button');
        button.type = 'button'; button.dataset.processingTab = key;
        button.innerHTML = `<span>${group.icon}</span>${group.label}`;
        tabbar.appendChild(button);
        const panel = document.createElement('section');
        panel.className = 'processing-admin-tab-panel'; panel.dataset.processingTabPanel = key;
        panelHost.appendChild(panel); panels[key] = panel;
      });
      headings[0].before(tabbar, panelHost);
      headings.forEach((heading, index) => {
        const groupKey = Object.entries(groups).find(([, group]) => group.headings.includes(heading.textContent.trim()))?.[0];
        if (!groupKey) return;
        const end = headings[index + 1];
        const nodes = [heading];
        let node = heading.nextElementSibling;
        while (node && node !== end) { nodes.push(node); node = node.nextElementSibling; }
        nodes.forEach(item => panels[groupKey].appendChild(item));
      });
      const activateProcessingTab = key => {
        const selected = panels[key] ? key : 'buildings';
        Object.entries(panels).forEach(([panelKey, panel]) => { panel.hidden = panelKey !== selected; });
        tabbar.querySelectorAll('button').forEach(button => button.setAttribute('aria-current', button.dataset.processingTab === selected ? 'page' : 'false'));
        localStorage.setItem('animalFarmProcessingAdminTab', selected);
      };
      tabbar.addEventListener('click', event => {
        const button = event.target.closest('button[data-processing-tab]');
        if (button) activateProcessingTab(button.dataset.processingTab);
      });
      activateProcessingTab(localStorage.getItem('animalFarmProcessingAdminTab') || 'buildings');
    }
  }

  document.querySelectorAll('[data-recipe-input-builder]').forEach(builder => {
    const rows = builder.querySelector('[data-ingredient-rows]');
    const template = builder.querySelector('template');
    const updateRemoveControls = () => {
      const controls = rows.querySelectorAll('[data-remove-ingredient]');
      controls.forEach(button => { button.disabled = controls.length === 1; });
    };
    builder.querySelector('[data-add-ingredient]')?.addEventListener('click', () => {
      rows.appendChild(template.content.cloneNode(true));
      updateRemoveControls();
    });
    rows.addEventListener('click', event => {
      const button = event.target.closest('[data-remove-ingredient]');
      if (!button || button.disabled) return;
      button.closest('.ingredient-row')?.remove();
      updateRemoveControls();
    });
    updateRemoveControls();
  });
  document.querySelectorAll('[data-confirm-action]').forEach(button => button.addEventListener('click', event => {
    if (!window.confirm(button.dataset.confirmAction)) event.preventDefault();
  }));
})();
