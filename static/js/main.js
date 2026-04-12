// WatchParty — main.js
document.addEventListener('DOMContentLoaded', () => {
    // ===== FLASH MESSAGES =====
    const flashMessages = document.querySelectorAll('.flash-item');
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach((msg, i) => {
                setTimeout(() => {
                    msg.style.transition = 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
                    msg.style.opacity = '0';
                    msg.style.transform = 'translateX(40px)';
                    setTimeout(() => msg.remove(), 400);
                }, i * 150);
            });
        }, 4000);
    }

    // ===== HEADER SCROLL EFFECT =====
    const header = document.getElementById('mainHeader');
    if (header) {
        window.addEventListener('scroll', () => {
            header.classList.toggle('scrolled', window.scrollY > 50);
        }, { passive: true });
    }

    // ===== SCROLL REVEAL =====
    const revealElements = document.querySelectorAll('.reveal');
    if (revealElements.length > 0) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

        revealElements.forEach(el => observer.observe(el));
    }

    // ===== MOBILE NAV TOGGLE =====
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const primaryNav = document.querySelector('.primary-nav');
    if (mobileMenuBtn && primaryNav) {
        mobileMenuBtn.addEventListener('click', () => {
            primaryNav.classList.toggle('mobile-open');
        });
    }

    // ===== SMART THUMBNAIL FIT =====
    // For images with unusual dimensions, switch to contain mode to avoid ugly crops.
    const smartThumbs = document.querySelectorAll('img[data-smart-thumb]');
    smartThumbs.forEach((img) => {
        const applyFit = () => {
            const w = img.naturalWidth || 0;
            const h = img.naturalHeight || 0;
            if (!w || !h) return;
            const ratio = w / h;
            const targetRatio = parseFloat(img.dataset.thumbRatio || '0.67');
            const tooWide = ratio > (targetRatio * 1.55);
            const tooTall = ratio < (targetRatio * 0.55);
            img.classList.toggle('smart-thumb-contain', tooWide || tooTall);
        };

        if (img.complete) {
            applyFit();
        } else {
            img.addEventListener('load', applyFit, { once: true });
        }
    });
});
