// static/js/app.js

document.addEventListener('DOMContentLoaded', async () => {
    // --- State & DOM Elements ---
    let allSplits = [];
    const dom = {
        dashboard: document.getElementById('dashboard'),
        sidebar: document.querySelector('.sidebar'),
        sidebarOverlay: document.getElementById('sidebar-overlay'),
        sidebarList: document.getElementById('split-list-sidebar'),
        homeLink: document.getElementById('home-link'),
        welcomeMessage: document.getElementById('welcome-message'),
        iframeContainer: document.getElementById('iframe-container'),
        mobileSplitView: document.getElementById('mobile-split-view'),
        managementView: document.getElementById('management-view'),
        collapseBtn: document.getElementById('collapse-btn'),
        themeButtons: document.querySelectorAll('.theme-btn'),
        manageBtn: document.getElementById('manage-btn'),
        hamburgerBtn: document.getElementById('hamburger-btn'),
        closeSidebarBtn: document.getElementById('close-sidebar-btn'),
        mobilePageTitle: document.getElementById('mobile-page-title'),
        htmlElement: document.documentElement
    };

    const isMobile = () => window.innerWidth < 769;

    // --- Fonctions de base ---
    const createSlug = (text) => text.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    const api = { getSplits: async()=>(await fetch('/api/splits')).json(), add: async(d)=>(await fetch('/api/splits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})).json(), update: async(i,d)=>(await fetch(`/api/splits/${i}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})).json(), delete: async(i)=>(await fetch(`/api/splits/${i}`,{method:'DELETE'})).json(), };
    const applyTheme = (theme) => { if(theme){dom.htmlElement.dataset.theme = theme;localStorage.setItem('dashboard-theme', theme);dom.themeButtons.forEach(btn=>btn.classList.toggle('active', btn.dataset.theme === theme));} };

    // --- Fonctions de rendu UI ---
    const renderNavUI = () => { dom.sidebarList.innerHTML = ''; const icon = `<i class="fa-solid fa-snowflake"></i>`; allSplits.forEach(split => { const li = document.createElement('li'); li.dataset.name = split.name; li.innerHTML = `${icon} <span>${split.label}</span>`; li.addEventListener('click', () => { navigateTo(`/split/${split.name}`); if (isMobile()) toggleSidebar(false); }); dom.sidebarList.appendChild(li); }); };
    const formHTML = (split = {}) => { return `<form id="split-form" data-id="${split.id || ''}"><h3>${split.id ? 'Modifier le Split' : 'Ajouter un Split'}</h3><div class="form-group"><label for="label">Nom affiché</label><input type="text" id="label" name="label" value="${split.label || ''}" required></div><div class="form-group"><label for="url">Adresse IP (ex: http://192.168.1.190)</label><input type="url" id="url" name="url" value="${split.url || ''}" required></div><div class="form-actions"><button type="submit">${split.id ? 'Enregistrer' : 'Ajouter'}</button>${split.id ? '<button type="button" class="cancel-btn">Annuler</button>' : ''}</div></form>`; };
    const renderManagementView = () => { let listHTML = '<ul>'; allSplits.forEach(s => { listHTML += `<li data-id="${s.id}"><div class="split-info"><strong>${s.label}</strong><span>${s.url}</span></div><div class="split-actions"><button class="edit-btn" title="Modifier"><i class="fa-solid fa-pencil"></i></button><button class="delete-btn" title="Supprimer"><i class="fa-solid fa-trash"></i></button></div></li>`; }); listHTML += '</ul>'; dom.managementView.innerHTML = `<h2>Gestion des Splits</h2><div id="form-container">${formHTML()}</div><div id="list-container"><h3>Liste</h3>${listHTML}</div>`; attachManagementListeners(); };
    const attachManagementListeners = () => { const form = dom.managementView.querySelector('#split-form'); if(form) form.addEventListener('submit', async (e) => { e.preventDefault(); const fd = new FormData(form), id = form.dataset.id; const data = {label: fd.get('label'), url: fd.get('url'), name: createSlug(fd.get('label'))}; if (id) { await api.update(id, data); allSplits = allSplits.map(s => s.id == id ? {...s, ...data, id: s.id} : s); } else { const n = await api.add(data); allSplits.push(n); } renderNavUI(); renderManagementView(); }); const list = dom.managementView.querySelector('#list-container ul'); if(list) list.addEventListener('click', async (e) => { const ed = e.target.closest('.edit-btn'), del = e.target.closest('.delete-btn'); if (ed) { const id = ed.closest('li').dataset.id; const s = allSplits.find(sp => sp.id == id); dom.managementView.querySelector('#form-container').innerHTML = formHTML(s); attachManagementListeners(); } if (del && confirm('Êtes-vous sûr ?')) { const id = del.closest('li').dataset.id; await api.delete(id); allSplits = allSplits.filter(s => s.id != id); renderNavUI(); renderManagementView(); } }); const cancel = dom.managementView.querySelector('.cancel-btn'); if(cancel) cancel.addEventListener('click', () => renderManagementView()); };

    // --- Gestion de la Sidebar ---
    const toggleSidebar = (forceOpen) => { const isOpen = dom.sidebar.classList.contains('is-open'); const show = forceOpen === undefined ? !isOpen : forceOpen; dom.sidebar.classList.toggle('is-open', show); dom.sidebarOverlay.classList.toggle('is-active', show); };

    // --- Routing & Navigation ---
    const navigateTo = (path) => { window.history.pushState({}, '', path); handleRouteChange(); };

    const handleRouteChange = () => {
        const path = window.location.pathname;
        const mainViews = [dom.welcomeMessage, dom.iframeContainer, dom.managementView, dom.mobileSplitView];
        mainViews.forEach(v => v.style.display = 'none');
        dom.sidebarList.querySelectorAll('li').forEach(li => li.classList.remove('active'));
        let pageTitle = "Dashboard";

        if (path.startsWith('/split/')) {
            const splitName = path.substring(7);
            const split = allSplits.find(s => s.name === splitName);
            if (split) {
                pageTitle = split.label;
                const activeLi = dom.sidebarList.querySelector(`li[data-name="${split.name}"]`);
                if(activeLi) activeLi.classList.add('active');

                // MODIFICATION : On utilise la variable globale pour construire l'URL
                const subDomainUrl = `${window.location.protocol}//${split.name}.${window.SPLIT_BASE_DOMAIN}`;

                if (isMobile()) {
                    dom.mobileSplitView.style.display = 'block';
                    dom.mobileSplitView.innerHTML = `<div class="mobile-split-card"><h2>${split.label}</h2><a href="${subDomainUrl}" target="_blank" class="control-btn">Ouvrir le panneau</a></div>`;
                } else {
                    dom.iframeContainer.style.display = 'flex';
                    dom.iframeContainer.innerHTML = `<iframe id="split-iframe" src="${subDomainUrl}" title="Panneau de contrôle"></iframe>`;
                }
            } else { navigateTo('/'); }
        } else if (path === '/manage') {
            pageTitle = "Gestion des Splits";
            dom.managementView.style.display = 'block';
            renderManagementView();
        } else {
            dom.welcomeMessage.style.display = 'flex';
        }
        dom.mobilePageTitle.textContent = pageTitle;
        applyTheme(localStorage.getItem('dashboard-theme') || 'system');
    };

    // --- Initialisation de l'application ---
    const initApp = async () => {
        dom.hamburgerBtn.addEventListener('click', () => toggleSidebar());
        dom.closeSidebarBtn.addEventListener('click', () => toggleSidebar(false));
        dom.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));
        dom.collapseBtn.addEventListener('click', () => dom.dashboard.classList.toggle('collapsed'));
        dom.themeButtons.forEach(btn => { btn.addEventListener('click', (e) => applyTheme(e.currentTarget.dataset.theme)); });
        dom.manageBtn.addEventListener('click', (e) => { e.preventDefault(); navigateTo('/manage'); if (isMobile()) toggleSidebar(false); });
        dom.homeLink.addEventListener('click', (e) => { e.preventDefault(); navigateTo('/'); if (isMobile()) { toggleSidebar(false); } });
        window.addEventListener('popstate', handleRouteChange);

        try {
            allSplits = await api.getSplits();
            renderNavUI();
            handleRouteChange();
        }
        catch (error) {
            console.error("Erreur d'initialisation:", error);
            dom.sidebarList.innerHTML = '<li style="padding: 1rem;">Erreur de chargement.</li>';
            dom.welcomeMessage.querySelector('h2').textContent = "Erreur de connexion.";
        } finally {
            dom.sidebarList.classList.add('is-loaded');
        }
    };

    initApp();
});