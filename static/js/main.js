// Smart Body Worn Camera - Frontend Logic

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const API = (url, opts = {}) =>
    fetch(url, { headers: { "Content-Type": "application/json" }, ...opts })
        .then(r => { if (r.status === 401) window.location = "/login"; return r.json(); });

// ── Login ─────────────────────────────────────────────────────────────
function showRegister() { $("#loginPanel").classList.add("hidden"); $("#registerPanel").classList.remove("hidden"); }
function showLogin() { $("#registerPanel").classList.add("hidden"); $("#loginPanel").classList.remove("hidden"); }

async function doLogin() {
    const r = await API("/api/login", {
        method: "POST",
        body: JSON.stringify({ username: $("#loginUser").value, password: $("#loginPass").value })
    });
    if (r.error) return showMsg("#loginMsg", r.error, true);
    window.location = "/live";
}

async function doRegister() {
    const p = $("#regPass").value;
    if (p !== $("#regConfirm").value) return showMsg("#loginMsg", "两次密码不一致", true);
    const r = await API("/api/register", {
        method: "POST",
        body: JSON.stringify({ username: $("#regUser").value, password: p, realName: $("#regName").value })
    });
    if (r.error) return showMsg("#loginMsg", r.error, true);
    showMsg("#loginMsg", r.message, false);
    setTimeout(showLogin, 1500);
}

function showMsg(elId, text, isErr) {
    const el = $(elId); if (!el) return;
    el.textContent = text; el.className = "msg " + (isErr ? "msg-error" : "msg-success");
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
}

// ── Camera ────────────────────────────────────────────────────────────
if (window.location.pathname === "/live") {
    document.addEventListener("DOMContentLoaded", async () => {
        const r = await API("/api/camera/status");
        updateCameraUI(r);
    });
    setInterval(async () => {
        const r = await API("/api/camera/status");
        updateCameraUI(r);
    }, 2000);
}

function updateCameraUI(status) {
    const camOpen = status.camera_open;
    const rec = status.recording;

    $("#camDot").className = "status-dot" + (camOpen ? " active" : "");
    $("#camStatus").textContent = camOpen ? "摄像头已连接" : "未连接";

    $("#btnStartCam").disabled = camOpen;
    $("#btnStopCam").disabled = !camOpen;
    $("#btnPhoto").disabled = !camOpen || rec;
    $("#btnRecord").disabled = !camOpen;

    if (rec) {
        $("#btnRecord").textContent = "停止录制";
        $("#btnRecord").classList.add("recording");
        $("#recDot").classList.remove("hidden");
        $("#recStatus").textContent = "录制中";
    } else {
        $("#btnRecord").textContent = "开始录制";
        $("#btnRecord").classList.remove("recording");
        $("#recDot").classList.add("hidden");
        $("#recStatus").textContent = "未录制";
    }

    if (!camOpen) $("#noFeed").classList.remove("hidden");
    else $("#noFeed").classList.add("hidden");
}

async function startCamera() {
    const r = await API("/api/camera/start", { method: "POST", body: JSON.stringify({ camera_id: 0 }) });
    if (r.ok) updateCameraUI(await (await API("/api/camera/status")));
    else alert("无法打开摄像头，请检查设备");
}

async function stopCamera() {
    await API("/api/camera/stop", { method: "POST" });
    updateCameraUI({ camera_open: false, recording: false });
}

async function takePhoto() {
    const r = await API("/api/camera/photo", { method: "POST" });
    if (r.error) alert(r.error);
    else alert("拍照成功: " + r.filename);
}

let isRecording = false;
async function toggleRecording() {
    if (!isRecording) {
        const r = await API("/api/camera/record/start", { method: "POST" });
        if (r.ok) isRecording = true;
        else alert("录制启动失败，请检查 FFmpeg");
    } else {
        const r = await API("/api/camera/record/stop", { method: "POST" });
        isRecording = false;
        alert("录制完成: " + (r.filename || ""));
    }
}

// ── Photos ────────────────────────────────────────────────────────────
if (window.location.pathname === "/photos") {
    document.addEventListener("DOMContentLoaded", loadPhotos);
}

async function loadPhotos() {
    if (!$("#photoGrid")) return;
    const r = await API("/api/photos");
    let html = "";
    r.forEach(p => {
        html += `<div class="photo-card" onclick="openLightbox('${p.url}')">
            <img src="${p.url}" alt="${p.filename}" loading="lazy">
            <div class="photo-info">${p.created_at}</div>
        </div>`;
    });
    $("#photoGrid").innerHTML = html || '<div style="color:var(--text2);grid-column:1/-1;text-align:center;padding:40px;">暂无照片</div>';
}

function openLightbox(url) {
    $("#lightboxImg").src = url;
    $("#lightbox").classList.remove("hidden");
}
function closeLightbox() { $("#lightbox").classList.add("hidden"); }

// ── Videos ────────────────────────────────────────────────────────────
if (window.location.pathname === "/videos") {
    document.addEventListener("DOMContentLoaded", loadVideos);
}

async function loadVideos() {
    if (!$("#videoTable")) return;
    const r = await API("/api/videos");
    let html = "", opts = "";
    r.forEach(v => {
        const sizeStr = v.size > 1048576 ? (v.size / 1048576).toFixed(1) + " MB" :
                        v.size > 1024 ? (v.size / 1024).toFixed(1) + " KB" : v.size + " B";
        html += `<tr>
            <td>${v.id}</td><td>${v.filename}</td><td>${v.format}</td><td>${v.duration}</td>
            <td>${sizeStr}</td><td>${v.created_at}</td>
            <td><button class="btn btn-outline btn-sm" onclick="playVideo('${v.url}')">播放</button></td>
        </tr>`;
        opts += `<option value="${v.id}">${v.filename}</option>`;
    });
    $("#videoTable tbody").innerHTML = html || '<tr><td colspan="7" style="text-align:center;color:var(--text2)">暂无视频</td></tr>';
    $("#transcodeVideo").innerHTML = opts;
}

function playVideo(url) {
    const vp = $("#videoPlayer");
    vp.src = url; vp.style.display = "block"; vp.play();
}

async function doTranscode() {
    const vid = $("#transcodeVideo").value;
    const fmt = $("#transcodeFormat").value;
    if (!vid) return;
    const r = await API("/api/videos/" + vid + "/transcode", {
        method: "POST", body: JSON.stringify({ format: fmt })
    });
    if (r.error) showMsg("#transcodeMsg", r.error, true);
    else showMsg("#transcodeMsg", "转码成功: " + r.output + " <a href=" + r.url + " target=_blank>下载</a>", false);
}

// ── Logs ──────────────────────────────────────────────────────────────
if (window.location.pathname === "/logs") {
    document.addEventListener("DOMContentLoaded", loadLogs);
}

async function loadLogs() {
    if (!$("#logTable")) return;
    const r = await API("/api/logs");
    let html = "";
    r.forEach(l => {
        html += `<tr><td>${l.id}</td><td>${l.action}</td><td>${l.detail}</td><td>${l.created_at}</td></tr>`;
    });
    $("#logTable tbody").innerHTML = html || '<tr><td colspan="4" style="text-align:center;color:var(--text2)">暂无日志</td></tr>';
}

$("#loginPass")?.addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); });
