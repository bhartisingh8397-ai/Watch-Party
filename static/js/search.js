document.addEventListener('DOMContentLoaded', () => {
    const searchWrap = document.getElementById('search-bar-container');
    const searchBtn = document.querySelector('.search-btn');
    const closeBtn = document.getElementById('closeSearch');
    const searchInput = document.getElementById('globalSearchInput');

    // Toggle Visibility
    const openSearch = () => {
        searchWrap.style.display = 'block';
        searchInput.focus();
    };

    const closeSearch = () => {
        searchWrap.style.display = 'none';
        searchInput.value = '';
        // Reset filters
        filterMovies('');
    };

    if (searchBtn) searchBtn.addEventListener('click', openSearch);
    if (closeBtn) closeBtn.addEventListener('click', closeSearch);

    // Escape to close
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && searchWrap.style.display === 'block') {
            closeSearch();
        }
    });

    // Filter Logic
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        filterMovies(query);
    });

    function filterMovies(query) {
        // 1. Filter Movie Library Cards
        const cards = document.querySelectorAll('.movie-card');
        cards.forEach(card => {
            const title = card.querySelector('h3').innerText.toLowerCase();
            if (title.includes(query)) {
                card.style.display = 'flex';
            } else {
                card.style.display = 'none';
            }
        });

        // 2. Filter Admin Dashboard Rows
        const rows = document.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const titleCell = row.querySelector('td:nth-child(2)'); // Title column
            if (titleCell) {
                const title = titleCell.innerText.toLowerCase();
                if (title.includes(query)) {
                    row.style.display = 'table-row';
                } else {
                    row.style.display = 'none';
                }
            }
        });
        
        // 3. Handle Empty States
        const visibleCards = document.querySelectorAll('.movie-card[style="display: flex;"]').length;
        const libraryGrid = document.querySelector('.movie-grid');
        if (libraryGrid && query !== '') {
            // Optional: show a "No results" message if visibleCards === 0
        }
    }
});
