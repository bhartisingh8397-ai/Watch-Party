document.addEventListener('DOMContentLoaded', () => {
    const searchWrap = document.getElementById('search-bar-container');
    const searchBtn = document.querySelector('.search-btn');
    const closeBtn = document.getElementById('closeSearch');
    const searchInput = document.getElementById('globalSearchInput');

    if (!searchWrap || !searchInput) return;

    // Toggle Visibility
    const openSearch = () => {
        searchWrap.style.display = 'block';
        searchInput.focus();
    };

    const closeSearch = () => {
        searchWrap.style.display = 'none';
        searchInput.value = '';
        filterContent('');
    };

    if (searchBtn) searchBtn.addEventListener('click', openSearch);
    if (closeBtn) closeBtn.addEventListener('click', closeSearch);

    // Escape to close
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && searchWrap.style.display === 'block') {
            closeSearch();
        }
        // Ctrl+K to open search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            openSearch();
        }
    });

    // Filter Logic
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        filterContent(query);
    });

    function filterContent(query) {
        let hasVisibleCards = false;
        let hasVisibleRows = false;

        // 1. Filter Movie Library Cards
        const cards = document.querySelectorAll('.movie-card');
        cards.forEach(card => {
            const titleEl = card.querySelector('h3');
            if (!titleEl) return;
            const title = titleEl.innerText.toLowerCase();
            const visible = !query || title.includes(query);
            card.style.display = visible ? 'flex' : 'none';
            if (visible) hasVisibleCards = true;
        });

        // 2. Filter Admin Dashboard Rows
        const rows = document.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const titleCell = row.querySelector('td:nth-child(2)');
            if (titleCell) {
                const title = titleCell.innerText.toLowerCase();
                const visible = !query || title.includes(query);
                row.style.display = visible ? 'table-row' : 'none';
                if (visible) hasVisibleRows = true;
            }
        });

        // 3. Filter Room Cards
        const roomCards = document.querySelectorAll('.room-card-premium');
        roomCards.forEach(card => {
            const titleEl = card.querySelector('h3');
            if (!titleEl) return;
            const title = titleEl.innerText.toLowerCase();
            const visible = !query || title.includes(query);
            card.closest('a').style.display = visible ? 'block' : 'none';
        });

        // 4. Handle "No results" message
        const movieGrid = document.querySelector('.movie-grid');
        if (movieGrid && query) {
            let noResultsMsg = movieGrid.querySelector('.no-results-msg');
            if (!hasVisibleCards && cards.length > 0) {
                if (!noResultsMsg) {
                    noResultsMsg = document.createElement('div');
                    noResultsMsg.className = 'no-results-msg';
                    noResultsMsg.innerHTML = `<p>No movies found for "<strong>${query}</strong>"</p>`;
                    movieGrid.appendChild(noResultsMsg);
                } else {
                    noResultsMsg.innerHTML = `<p>No movies found for "<strong>${query}</strong>"</p>`;
                    noResultsMsg.style.display = 'block';
                }
            } else if (noResultsMsg) {
                noResultsMsg.style.display = 'none';
            }
        }
    }
});
