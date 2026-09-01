(() => {
  const render = () => document.querySelectorAll('[data-until]').forEach(node => {
    const seconds = Math.max(0, Math.floor((new Date(node.dataset.until).getTime() - Date.now()) / 1000));
    const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), secs = seconds % 60;
    node.textContent = seconds ? `${node.dataset.prefix || ''}${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')}:${String(secs).padStart(2,'0')}` : 'Ready now';
  });
  render(); setInterval(render, 1000); setInterval(() => { if (!document.querySelector('dialog[open]')) location.reload(); }, 60000);
  document.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.open)?.showModal()));
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog')?.close()));
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  const marketTabs = [...document.querySelectorAll('[data-market-tab]')];
  const marketPanels = [...document.querySelectorAll('[data-market-panel]')];
  const activateMarketTab = tab => {
    marketTabs.forEach(item => item.setAttribute('aria-selected', String(item === tab)));
    marketPanels.forEach(panel => { panel.hidden = panel.dataset.marketPanel !== tab.dataset.marketTab; });
  };
  marketTabs.forEach(tab => tab.addEventListener('click', () => activateMarketTab(tab)));
  const requestedMarketTab = new URLSearchParams(location.search).get('market');
  if (requestedMarketTab) {
    const tab = marketTabs.find(item => item.dataset.marketTab === requestedMarketTab);
    if (tab) activateMarketTab(tab);
  }
  const requestedDialog = new URLSearchParams(location.search).get('open');
  if (requestedDialog) {
    const dialog = document.getElementById(requestedDialog), alert = document.querySelector('.game-alert');
    if (dialog) {
      if (alert) dialog.prepend(alert);
      requestAnimationFrame(() => dialog.showModal());
    }
  }

  const panelConfig = {
    fishery: { icon: '🐟', label: 'Fishery', title: 'Ponds & fishery' },
    'my-animals': { icon: '🐾', label: 'My animals', title: 'My animals' },
    inventory: { icon: '🎒', label: 'Inventory', title: 'Farm inventory' },
    deliveries: { icon: '🚚', label: 'Deliveries', title: 'Market deliveries' },
    ledger: { icon: '📒', label: 'Ledger', title: 'Farmies ledger' }
  };
  const panels = [...document.querySelectorAll('[data-game-panel]')];
  if (panels.length) {
    document.body.classList.add('has-game-rail');
    const rail = document.createElement('aside'); rail.className = 'game-tool-rail'; rail.setAttribute('aria-label', 'Farm management tools');
    const marketDialog = document.getElementById('market-dialog');
    if (marketDialog) {
      const marketTrigger = document.createElement('button');
      marketTrigger.type = 'button'; marketTrigger.className = 'game-tool game-tool-market';
      marketTrigger.setAttribute('aria-label', 'Open Marketplace'); marketTrigger.setAttribute('aria-controls', marketDialog.id);
      marketTrigger.innerHTML = '<span aria-hidden="true">🏪</span><small>Market</small>';
      marketTrigger.addEventListener('click', () => marketDialog.showModal());
      rail.appendChild(marketTrigger);
    }
    panels.forEach(panel => {
      const key = panel.dataset.gamePanel, config = panelConfig[key];
      if (!config) return;
      const dialog = document.createElement('dialog'); dialog.className = 'game-screen-dialog'; dialog.id = `${key}-screen`;
      const header = document.createElement('header'); header.className = 'game-screen-header';
      const heading = document.createElement('div'); heading.innerHTML = `<span>${config.icon}</span><div><small>FARM CONTROL</small><h2>${config.title}</h2></div>`;
      const close = document.createElement('button'); close.type = 'button'; close.className = 'game-screen-close'; close.setAttribute('aria-label', `Close ${config.label}`); close.textContent = '×';
      close.addEventListener('click', () => dialog.close()); header.append(heading, close);
      const content = document.createElement('div'); content.className = 'game-screen-content'; panel.classList.add('is-dialog-panel'); content.appendChild(panel); dialog.append(header, content); document.body.appendChild(dialog);
      if (requestedDialog === dialog.id) {
        const alert = document.querySelector('.game-alert');
        if (alert) content.prepend(alert);
        requestAnimationFrame(() => dialog.showModal());
      }
      const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = `game-tool game-tool-${key}`; trigger.dataset.label = config.label; trigger.setAttribute('aria-label', `Open ${config.label}`); trigger.setAttribute('aria-controls', dialog.id); trigger.innerHTML = `<span aria-hidden="true">${config.icon}</span><small>${config.label}</small>`;
      trigger.addEventListener('click', () => dialog.showModal()); rail.appendChild(trigger);
    });
    document.body.appendChild(rail);
  }
  if (requestedDialog) {
    const cleanUrl = new URL(location.href);
    cleanUrl.searchParams.delete('open');
    cleanUrl.searchParams.delete('market');
    history.replaceState(history.state, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`);
  }
})();
