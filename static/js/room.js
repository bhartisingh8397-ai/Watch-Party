const socket = io();
const player = videojs('watchVideo', {
    autoplay: false,
    controls: true,
    responsive: true,
    fluid: true,
    playbackRates: [0.5, 1, 1.5, 2]
});

const errorMsg = document.getElementById('playback-error-msg');
const roomSyncToast = document.getElementById('roomSyncToast');
const resyncBtn = document.getElementById('resyncBtn');

// Join room
socket.emit('join', { room: ROOM_ID, username: USERNAME });

// Error handling for unsupported formats
player.on('error', function() {
    console.error('Video.js Error:', player.error());
    errorMsg.style.display = 'block';
    const tech = document.querySelector('.vjs-tech');
    if (tech) tech.style.opacity = '0.2';
});

// Syncing Video
let isRemoteChange = false;
let pendingRoomState = null;
let toastTimer = null;

function showRoomSyncToast(message) {
    if (!roomSyncToast) return;
    roomSyncToast.textContent = message || 'Synced to room time';
    roomSyncToast.style.display = 'block';
    requestAnimationFrame(() => {
        roomSyncToast.classList.add('is-visible');
    });
    if (toastTimer) {
        clearTimeout(toastTimer);
    }
    toastTimer = setTimeout(() => {
        roomSyncToast.classList.remove('is-visible');
        setTimeout(() => {
            roomSyncToast.style.display = 'none';
        }, 220);
    }, 1800);
}

function applyVideoEvent(data) {
    if (!data || typeof data.time !== 'number') return;
    isRemoteChange = true;
    if (data.type === 'play') {
        player.currentTime(data.time);
        player.play();
    } else if (data.type === 'pause') {
        player.pause();
    } else if (data.type === 'seek') {
        player.currentTime(data.time);
    }
}

function applyRoomState(data) {
    if (!data || typeof data.time !== 'number') return;
    isRemoteChange = true;
    player.currentTime(data.time);
    if (data.type === 'play') {
        player.play();
    } else if (data.type === 'pause') {
        player.pause();
    }
}

player.on('play', () => {
    if (!isRemoteChange) {
        socket.emit('sync_video', { room: ROOM_ID, type: 'play', time: player.currentTime() });
    }
    isRemoteChange = false;
});

player.on('pause', () => {
    if (!isRemoteChange) {
        socket.emit('sync_video', { room: ROOM_ID, type: 'pause', time: player.currentTime() });
    }
    isRemoteChange = false;
});

player.on('seeked', () => {
    if (!isRemoteChange) {
        socket.emit('sync_video', { room: ROOM_ID, type: 'seek', time: player.currentTime() });
    }
    isRemoteChange = false;
});

socket.on('video_event', (data) => {
    applyVideoEvent(data);
});

socket.on('video_state', (data) => {
    if (!data || typeof data.time !== 'number') return;
    if (player.readyState() < 1) {
        pendingRoomState = data;
        return;
    }
    applyRoomState(data);
    showRoomSyncToast(`Synced to room time (${formatTime(data.time)})`);
});

player.on('loadedmetadata', () => {
    if (pendingRoomState) {
        applyRoomState(pendingRoomState);
        showRoomSyncToast(`Synced to room time (${formatTime(pendingRoomState.time)})`);
        pendingRoomState = null;
    }
});

if (resyncBtn) {
    resyncBtn.addEventListener('click', () => {
        socket.emit('request_video_state', { room: ROOM_ID });
        showRoomSyncToast('Re-sync requested...');
    });
}

// Chat & UI Interactions
const chatInput = document.getElementById('chatInput');
const sendMessage = document.getElementById('sendMessage');
const chatBox = document.getElementById('chatBox');

function sendChatMessage() {
    const msg = chatInput.value.trim();
    if (msg) {
        socket.emit('chat_message', { room: ROOM_ID, username: USERNAME, message: msg });
        socket.emit('stop_typing', { room: ROOM_ID, username: USERNAME });
        chatInput.value = '';
    }
}

sendMessage.addEventListener('click', sendChatMessage);

// Enter key sends chat message
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendChatMessage();
    }
});

// Typing Indicator
let typingTimeout;
const typingIndicator = document.getElementById('typingIndicator');
const typingUser = document.getElementById('typingUser');

chatInput.addEventListener('input', () => {
    socket.emit('typing', { room: ROOM_ID, username: USERNAME });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        socket.emit('stop_typing', { room: ROOM_ID, username: USERNAME });
    }, 2000);
});

socket.on('user_typing', (data) => {
    if (typingIndicator && typingUser) {
        typingUser.textContent = data.username;
        typingIndicator.style.display = 'flex';
    }
});

socket.on('user_stop_typing', (data) => {
    if (typingIndicator) {
        typingIndicator.style.display = 'none';
    }
});

socket.on('message', (data) => {
    const div = document.createElement('div');
    div.classList.add('chat-message');
    
    // Determine if this is a sent or received message
    if (data.username === USERNAME) {
        div.classList.add('chat-message-sent');
    } else {
        div.classList.add('chat-message-received');
    }
    
    div.innerHTML = `<span class="chat-username">${data.username}</span><span class="chat-text">${data.msg}</span>`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
});

// Danmaku (Type on screen)
const danmakuInput = document.getElementById('danmakuInput');
const sendDanmaku = document.getElementById('sendDanmaku');
const danmakuContainer = document.getElementById('danmakuContainer');

function sendDanmakuMessage() {
    const text = danmakuInput.value.trim();
    if (text) {
        socket.emit('on_screen_text', { room: ROOM_ID, text: text, color: 'white' });
        danmakuInput.value = '';
    }
}

sendDanmaku.addEventListener('click', sendDanmakuMessage);

// Enter key sends danmaku
danmakuInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendDanmakuMessage();
    }
});

socket.on('danmaku', (data) => {
    const item = document.createElement('div');
    item.classList.add('danmaku-item');
    item.innerText = data.text;
    item.style.top = Math.random() * 80 + '%';
    item.style.color = data.color || 'white';
    danmakuContainer.appendChild(item);
    setTimeout(() => item.remove(), 8000);
});

// Reactions
const reactionContainer = document.getElementById('reactionContainer');
const emojiBtns = document.querySelectorAll('.emoji-btn');

emojiBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const emoji = btn.getAttribute('data-emoji');
        socket.emit('reaction', { room: ROOM_ID, emoji: emoji });
    });
});

socket.on('reaction_burst', (data) => {
    const burst = document.createElement('div');
    burst.classList.add('reaction-burst');
    burst.innerText = data.emoji;
    burst.style.right = Math.random() * 50 + 'px';
    reactionContainer.appendChild(burst);
    setTimeout(() => burst.remove(), 2000);
});

// User Count & Active Users Panel
const userCountText = document.getElementById('userCountText');
const activeUsersList = document.getElementById('activeUsersList');
const activeUserCount = document.getElementById('activeUserCount');
const toggleActiveUsers = document.getElementById('toggleActiveUsers');
const chevronIcon = document.getElementById('chevronIcon');

let usersListOpen = true;

if (toggleActiveUsers) {
    toggleActiveUsers.addEventListener('click', () => {
        usersListOpen = !usersListOpen;
        activeUsersList.classList.toggle('collapsed', !usersListOpen);
        chevronIcon.style.transform = usersListOpen ? 'rotate(0deg)' : 'rotate(-90deg)';
    });
}

socket.on('user_count', (data) => {
    const count = data.count;
    const users = data.users || [];

    // Update top status bar count
    if (userCountText) {
        userCountText.innerHTML = `<span style="width: 8px; height: 8px; background: #2ecc71; border-radius: 50%; display: inline-block; box-shadow: 0 0 10px #2ecc71;"></span> ${count} Watching`;
    }

    // Update active count badge
    if (activeUserCount) {
        activeUserCount.textContent = count;
    }

    // Render active users list
    if (activeUsersList) {
        activeUsersList.innerHTML = '';
        users.forEach(user => {
            const userItem = document.createElement('div');
            userItem.classList.add('active-user-item');
            
            // Highlight current user
            if (user === USERNAME) {
                userItem.classList.add('is-you');
            }

            const initial = user.charAt(0).toUpperCase();
            const colors = ['#D4AF37', '#2ecc71', '#3498db', '#e74c3c', '#9b59b6', '#1abc9c', '#f39c12', '#e67e22'];
            const color = colors[user.charCodeAt(0) % colors.length];

            userItem.innerHTML = `
                <div class="user-avatar-sm" style="background: ${color}20; color: ${color}; border: 1px solid ${color}50;">
                    ${initial}
                </div>
                <span class="user-name-label">${user}${user === USERNAME ? ' (You)' : ''}</span>
                <span class="user-online-dot"></span>
            `;
            activeUsersList.appendChild(userItem);
        });
    }
});

// Real-Time Video Playback Status
function formatTime(seconds) {
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min < 10 ? '0' : ''}${min}:${sec < 10 ? '0' : ''}${sec}`;
}

const videoTimeStatus = document.getElementById('videoTimeStatus');
player.on('timeupdate', () => {
    if (videoTimeStatus) {
        const current = formatTime(player.currentTime());
        const duration = formatTime(player.duration() || 0);
        videoTimeStatus.innerText = `${current} / ${duration}`;
    }
});

// Status messages
socket.on('status', (data) => {
    const div = document.createElement('div');
    div.style.fontStyle = 'italic';
    div.style.color = 'var(--text-muted)';
    div.classList.add('chat-message', 'chat-message-status');
    div.innerText = data.msg;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
});

// Cinematic Remote Action Listeners
const remotePlay = document.getElementById('remotePlay');
const remotePause = document.getElementById('remotePause');
const remoteStop = document.getElementById('remoteStop');
const remoteFullscreen = document.getElementById('remoteFullscreen');

if (remotePlay) {
    remotePlay.addEventListener('click', () => player.play());
}
if (remotePause) {
    remotePause.addEventListener('click', () => player.pause());
}
if (remoteStop) {
    remoteStop.addEventListener('click', () => {
        player.currentTime(0);
        player.pause();
        socket.emit('sync_video', { room: ROOM_ID, type: 'seek', time: 0 });
    });
}
if (remoteFullscreen) {
    remoteFullscreen.addEventListener('click', () => {
        if (player.isFullscreen()) {
            player.exitFullscreen();
        } else {
            player.requestFullscreen();
        }
    });
}

// ===== SUBTITLE / CC TOGGLE =====
if (typeof HAS_SUBTITLE !== 'undefined' && HAS_SUBTITLE) {
    const subtitleToggle = document.getElementById('subtitleToggle');
    let subtitlesOn = true; // Default on since we used "default" attribute

    // Ensure text track is showing by default
    player.ready(() => {
        const tracks = player.textTracks();
        for (let i = 0; i < tracks.length; i++) {
            if (tracks[i].kind === 'captions' || tracks[i].kind === 'subtitles') {
                tracks[i].mode = 'showing';
            }
        }
        if (subtitleToggle) {
            subtitleToggle.classList.add('cc-active');
        }
    });

    if (subtitleToggle) {
        subtitleToggle.addEventListener('click', () => {
            subtitlesOn = !subtitlesOn;
            const tracks = player.textTracks();
            for (let i = 0; i < tracks.length; i++) {
                if (tracks[i].kind === 'captions' || tracks[i].kind === 'subtitles') {
                    tracks[i].mode = subtitlesOn ? 'showing' : 'disabled';
                }
            }
            subtitleToggle.classList.toggle('cc-active', subtitlesOn);
        });
    }
}

// ===== INVITE LINK COPY =====
const inviteBtn = document.getElementById('inviteBtn');
if (inviteBtn) {
    inviteBtn.addEventListener('click', () => {
        const url = window.location.href;
        navigator.clipboard.writeText(url).then(() => {
            const originalText = inviteBtn.innerText;
            inviteBtn.innerText = 'Copied!';
            inviteBtn.style.background = '#2ecc71';
            
            setTimeout(() => {
                inviteBtn.innerText = originalText;
                inviteBtn.style.background = 'var(--primary)';
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy: ', err);
            alert('Room Link: ' + url);
        });
    });
}
