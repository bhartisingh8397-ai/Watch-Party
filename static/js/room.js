const socket = io();
const player = videojs('watchVideo', {
    autoplay: false,
    controls: true,
    responsive: true,
    fluid: true,
    playbackRates: [0.5, 1, 1.5, 2]
});

const errorMsg = document.getElementById('playback-error-msg');

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
    isRemoteChange = true;
    if (data.type === 'play') {
        player.currentTime(data.time);
        player.play();
    } else if (data.type === 'pause') {
        player.pause();
    } else if (data.type === 'seek') {
        player.currentTime(data.time);
    }
});

// Chat & UI Interactions
const chatInput = document.getElementById('chatInput');
const sendMessage = document.getElementById('sendMessage');
const chatBox = document.getElementById('chatBox');

sendMessage.addEventListener('click', () => {
    const msg = chatInput.value.trim();
    if (msg) {
        socket.emit('chat_message', { room: ROOM_ID, username: USERNAME, message: msg });
        chatInput.value = '';
    }
});

socket.on('message', (data) => {
    const div = document.createElement('div');
    div.classList.add('chat-message');
    div.innerHTML = `<span class="chat-username">${data.username}:</span> ${data.msg}`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
});

// Danmaku (Type on screen)
const danmakuInput = document.getElementById('danmakuInput');
const sendDanmaku = document.getElementById('sendDanmaku');
const danmakuContainer = document.getElementById('danmakuContainer');

sendDanmaku.addEventListener('click', () => {
    const text = danmakuInput.value.trim();
    if (text) {
        socket.emit('on_screen_text', { room: ROOM_ID, text: text, color: 'white' });
        danmakuInput.value = '';
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

// User Count Tracking with Status Dot UI
const userCountText = document.getElementById('userCountText');
socket.on('user_count', (data) => {
    if (userCountText) {
        userCountText.innerHTML = `<span style="width: 8px; height: 8px; background: #2ecc71; border-radius: 50%; display: inline-block; box-shadow: 0 0 10px #2ecc71;"></span> ${data.count} Watching`;
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
    div.classList.add('chat-message');
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
