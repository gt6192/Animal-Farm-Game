(() => {
  const sectionRules = [
    { key: 'settings', label: 'Game settings', icon: '⚙️', titles: ['GLOBAL SETTINGS'] },
    { key: 'animals', label: 'Animals', icon: '🐾', titles: ['NEW ANIMAL', 'MARKET & TIMING'] },
    { key: 'feed', label: 'Feed', icon: '🌾', titles: ['NEW FEED', 'FEED MARKET'] },
    { key: 'land', label: 'Land', icon: '🌱', titles: ['LAND'] },
    { key: 'progression', label: 'Levels & XP', icon: '⭐', titles: ['LEVELS & XP', 'MANUAL XP'] },
    { key: 'upgrades', label: 'Upgrades', icon: '🏗️', titles: ['INVENTORY & TRANSPORT LEVELS'] },
    { key: 'fishery', label: 'Fishery', icon: '🐟', titles: ['FISHERY CATALOG'] },
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
