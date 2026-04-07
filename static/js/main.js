// Global main.js for WatchParty
console.log('WatchParty initialized');

// Mobile navigation or other global UI logic could go here
document.addEventListener('DOMContentLoaded', () => {
    const flashMessages = document.querySelectorAll('.flash-item');
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(msg => {
                msg.style.transition = 'opacity 1s';
                msg.style.opacity = '0';
                setTimeout(() => msg.remove(), 1000);
            });
        }, 3000);
    }
});
