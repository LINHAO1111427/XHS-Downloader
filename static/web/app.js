const byId = (id) => document.getElementById(id);

const elements = {
    authView: byId("authView"),
    appView: byId("appView"),
    authTitle: byId("authTitle"),
    authSubtitle: byId("authSubtitle"),
    authModes: byId("authModes"),
    authModeInputs: document.querySelectorAll('input[name="authMode"]'),
    registerModeLabel: byId("registerModeLabel"),
    authForm: byId("authForm"),
    displayNameField: byId("displayNameField"),
    authDisplayName: byId("authDisplayName"),
    authEmail: byId("authEmail"),
    authPassword: byId("authPassword"),
    confirmPasswordField: byId("confirmPasswordField"),
    authConfirmPassword: byId("authConfirmPassword"),
    authSubmitButton: byId("authSubmitButton"),
    authMessage: byId("authMessage"),
    serviceStatus: byId("serviceStatus"),
    downloadRoot: byId("downloadRoot"),
    urlInput: byId("urlInput"),
    downloadButton: byId("downloadButton"),
    pasteButton: byId("pasteButton"),
    clearInputButton: byId("clearInputButton"),
    taskList: byId("taskList"),
    taskSummary: byId("taskSummary"),
    clearTasksButton: byId("clearTasksButton"),
    fileList: byId("fileList"),
    fileEmpty: byId("fileEmpty"),
    fileSearch: byId("fileSearch"),
    librarySummary: byId("librarySummary"),
    selectAllFiles: byId("selectAllFiles"),
    enhanceButton: byId("enhanceButton"),
    livePhotoButton: byId("livePhotoButton"),
    archiveButton: byId("archiveButton"),
    refreshLibraryButton: byId("refreshLibraryButton"),
    alibabaUrls: byId("alibabaUrls"),
    alibabaKeyword: byId("alibabaKeyword"),
    alibabaCollect: byId("alibabaCollect"),
    alibabaProducts: byId("alibabaProducts"),
    alibabaSummary: byId("alibabaSummary"),
    openFolderButton: byId("openFolderButton"),
    livePhotoBadge: byId("livePhotoBadge"),
    aiGenerationState: byId("aiGenerationState"),
    aiVisualCount: byId("aiVisualCount"),
    aiSourceText: byId("aiSourceText"),
    aiInstructions: byId("aiInstructions"),
    aiGenerationModes: document.querySelectorAll('input[name="aiGenerationMode"]'),
    aiImageOptions: byId("aiImageOptions"),
    aiImageSize: byId("aiImageSize"),
    aiImageQuality: byId("aiImageQuality"),
    generateAIButton: byId("generateAIButton"),
    generateAIButtonLabel: byId("generateAIButtonLabel"),
    clearAIOutputButton: byId("clearAIOutputButton"),
    copyAIOutputButton: byId("copyAIOutputButton"),
    aiOutput: byId("aiOutput"),
    aiImageResult: byId("aiImageResult"),
    generatedImageMeta: byId("generatedImageMeta"),
    generatedImagePreviewButton: byId("generatedImagePreviewButton"),
    generatedImagePreview: byId("generatedImagePreview"),
    generatedImageLivePhoto: byId("generatedImageLivePhoto"),
    generatedImageDownload: byId("generatedImageDownload"),
    aiSettingsButton: byId("aiSettingsButton"),
    adminUsersButton: byId("adminUsersButton"),
    adminUsersDialog: byId("adminUsersDialog"),
    userSummary: byId("userSummary"),
    registrationEnabled: byId("registrationEnabled"),
    userList: byId("userList"),
    accountButton: byId("accountButton"),
    accountInitial: byId("accountInitial"),
    accountDialog: byId("accountDialog"),
    accountMeta: byId("accountMeta"),
    profileForm: byId("profileForm"),
    profileDisplayName: byId("profileDisplayName"),
    passwordForm: byId("passwordForm"),
    currentPassword: byId("currentPassword"),
    newPassword: byId("newPassword"),
    confirmNewPassword: byId("confirmNewPassword"),
    logoutButton: byId("logoutButton"),
    aiSettingsDialog: byId("aiSettingsDialog"),
    aiSettingsForm: byId("aiSettingsForm"),
    aiConfigState: byId("aiConfigState"),
    aiBaseUrl: byId("aiBaseUrl"),
    aiApiKey: byId("aiApiKey"),
    clearAIKey: byId("clearAIKey"),
    aiModel: byId("aiModel"),
    aiImageModel: byId("aiImageModel"),
    aiProtocols: document.querySelectorAll('input[name="aiProtocol"]'),
    toggleAIKeyButton: byId("toggleAIKeyButton"),
    testAIButton: byId("testAIButton"),
    saveAIButton: byId("saveAIButton"),
    settingsButton: byId("settingsButton"),
    settingsDialog: byId("settingsDialog"),
    cookieForm: byId("cookieForm"),
    cookieInput: byId("cookieInput"),
    cookieState: byId("cookieState"),
    disclaimerDialog: byId("disclaimerDialog"),
    acceptDisclaimerButton: byId("acceptDisclaimerButton"),
    enhancementPanel: byId("enhancementPanel"),
    enhancementTitle: byId("enhancementTitle"),
    enhancementDetail: byId("enhancementDetail"),
    enhancementProgress: byId("enhancementProgress"),
    enhancementState: byId("enhancementState"),
    livePhotoPanel: byId("livePhotoPanel"),
    livePhotoTitle: byId("livePhotoTitle"),
    livePhotoDetail: byId("livePhotoDetail"),
    livePhotoState: byId("livePhotoState"),
    livePhotoDialog: byId("livePhotoDialog"),
    livePhotoForm: byId("livePhotoForm"),
    livePhotoMeta: byId("livePhotoMeta"),
    livePhotoImage: byId("livePhotoImage"),
    livePhotoVideo: byId("livePhotoVideo"),
    liveStartField: byId("liveStartField"),
    liveStartRange: byId("liveStartRange"),
    liveStartValue: byId("liveStartValue"),
    liveDurationRange: byId("liveDurationRange"),
    liveDurationValue: byId("liveDurationValue"),
    createLivePhotoButton: byId("createLivePhotoButton"),
    mediaViewerDialog: byId("mediaViewerDialog"),
    mediaViewerTitle: byId("mediaViewerTitle"),
    mediaViewerMeta: byId("mediaViewerMeta"),
    mediaViewerDownload: byId("mediaViewerDownload"),
    closeMediaViewerButton: byId("closeMediaViewerButton"),
    previousMediaButton: byId("previousMediaButton"),
    nextMediaButton: byId("nextMediaButton"),
    mediaStage: byId("mediaStage"),
    mediaViewerImage: byId("mediaViewerImage"),
    mediaViewerVideo: byId("mediaViewerVideo"),
    toast: byId("toast"),
};

const ENHANCEABLE_SUFFIXES = new Set(["jpeg", "jpg", "png", "webp", "m4v", "mov", "mp4"]);
const LIVE_PHOTO_SUFFIXES = new Set(["jpeg", "jpg", "png", "webp", "m4v", "mov", "mp4"]);
let currentState = null;
let libraryItems = [];
let enhancementTasks = [];
let livePhotoTasks = [];
let selectedFiles = new Set();
let toastTimer = null;
let previousTaskFingerprint = "";
let previousEnhancementFingerprint = "";
let previousLivePhotoFingerprint = "";
let currentMediaIndex = -1;
let livePhotoSource = null;
let currentUser = null;
let csrfToken = "";
let authStatus = { needs_setup: false, registration_enabled: true };
let pollTimers = [];
let authGeneration = 0;

function refreshIcons() {
    if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
}

class APIError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

async function api(path, options = {}) {
    const requestGeneration = authGeneration;
    const method = (options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method) && csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
    }
    const response = await fetch(path, {
        ...options,
        credentials: "same-origin",
        headers,
    });
    if (!response.ok) {
        let message = `请求失败 (${response.status})`;
        try { message = (await response.json()).detail || message; } catch (_) { /* no-op */ }
        if (response.status === 401 && !path.startsWith("/api/auth/") && requestGeneration === authGeneration) showAuth();
        throw new APIError(message, response.status);
    }
    return response.status === 204 ? null : response.json();
}

function showToast(message, error = false) {
    clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.className = `toast show${error ? " error" : ""}`;
    toastTimer = setTimeout(() => { elements.toast.className = "toast"; }, 3200);
}

function authMode() {
    return [...elements.authModeInputs].find((input) => input.checked)?.value || "login";
}

function renderAuthMode() {
    let mode = authMode();
    if (mode === "register" && !authStatus.registration_enabled) {
        elements.authModeInputs[0].checked = true;
        mode = "login";
    }
    const registering = mode === "register";
    elements.displayNameField.hidden = !registering;
    elements.confirmPasswordField.hidden = !registering;
    elements.authDisplayName.required = registering;
    elements.authConfirmPassword.required = registering;
    elements.authPassword.autocomplete = registering ? "new-password" : "current-password";
    elements.authTitle.textContent = registering ? (authStatus.needs_setup ? "创建管理员账号" : "创建账号") : "登录账号";
    elements.authSubtitle.textContent = registering ? "填写账号信息后进入工作台" : "使用你的账号进入工作台";
    elements.authSubmitButton.lastElementChild.textContent = registering ? "注册并进入" : "登录";
    elements.authSubmitButton.firstElementChild.setAttribute("data-lucide", registering ? "user-plus" : "log-in");
    elements.authMessage.textContent = authStatus.needs_setup && registering ? "首个注册账号将成为系统管理员" : "";
    elements.authMessage.classList.remove("error");
    refreshIcons();
}

function stopPolling() {
    pollTimers.forEach((timer) => clearInterval(timer));
    pollTimers = [];
}

function showAuth(message = "") {
    authGeneration += 1;
    stopPolling();
    currentUser = null;
    csrfToken = "";
    elements.appView.hidden = true;
    elements.authView.hidden = false;
    elements.authPassword.value = "";
    elements.authConfirmPassword.value = "";
    if (message) {
        elements.authMessage.textContent = message;
        elements.authMessage.classList.add("error");
    }
    elements.authEmail.focus();
}

function renderCurrentUser() {
    const admin = currentUser?.role === "admin";
    const firstCharacter = Array.from(currentUser?.display_name || "用户")[0] || "用";
    elements.accountInitial.textContent = firstCharacter.toLocaleUpperCase();
    elements.accountMeta.textContent = `${currentUser.email} · ${admin ? "管理员" : "普通用户"}`;
    elements.profileDisplayName.value = currentUser.display_name;
    elements.adminUsersButton.hidden = !admin;
    elements.aiSettingsButton.hidden = !admin;
    elements.settingsButton.hidden = !admin;
    elements.openFolderButton.hidden = !admin;
}

async function enterWorkspace(session) {
    authGeneration += 1;
    currentUser = session.user;
    csrfToken = session.csrf_token;
    elements.authView.hidden = true;
    elements.appView.hidden = false;
    renderCurrentUser();
    refreshIcons();
    stopPolling();
    try {
        await Promise.all([refreshState(), refreshLibrary(), refreshEnhancements(), refreshLivePhotos(), loadAIConfig(), loadAlibabaProducts()]);
    } catch (error) {
        if (error.status !== 401) showToast(error.message, true);
    }
    if (!currentUser) return;
    pollTimers = [
        setInterval(refreshState, 1000),
        setInterval(refreshEnhancements, 1000),
        setInterval(refreshLivePhotos, 1000),
        setInterval(refreshLibrary, 5000),
    ];
}

async function bootstrapAuthentication() {
    try {
        authStatus = await api("/api/auth/status");
    } catch (error) {
        showAuth("服务暂时不可用，请稍后重试");
        return;
    }
    elements.registerModeLabel.hidden = !authStatus.registration_enabled;
    if (authStatus.needs_setup) {
        elements.authModeInputs.forEach((input) => { input.checked = input.value === "register"; });
    }
    renderAuthMode();
    try {
        await enterWorkspace(await api("/api/auth/me"));
    } catch (error) {
        if (error.status !== 401) showAuth(error.message);
        else showAuth();
    }
}

async function submitAuthentication(event) {
    event.preventDefault();
    const registering = authMode() === "register";
    if (registering && elements.authPassword.value !== elements.authConfirmPassword.value) {
        elements.authMessage.textContent = "两次输入的密码不一致";
        elements.authMessage.classList.add("error");
        elements.authConfirmPassword.focus();
        return;
    }
    elements.authSubmitButton.disabled = true;
    elements.authMessage.textContent = registering ? "正在创建账号" : "正在登录";
    elements.authMessage.classList.remove("error");
    const payload = {
        email: elements.authEmail.value.trim(),
        password: elements.authPassword.value,
    };
    if (registering) payload.display_name = elements.authDisplayName.value.trim();
    try {
        const session = await api(registering ? "/api/auth/register" : "/api/auth/login", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        authStatus.needs_setup = false;
        elements.authForm.reset();
        await enterWorkspace(session);
    } catch (error) {
        elements.authMessage.textContent = error.message;
        elements.authMessage.classList.add("error");
    } finally {
        elements.authSubmitButton.disabled = false;
    }
}

function accountTime(value) {
    return value ? formatTime(value) : "尚未登录";
}

function renderUsers(users) {
    elements.userList.replaceChildren();
    elements.userSummary.textContent = `${users.length} 个账号`;
    users.forEach((user) => {
        const row = document.createElement("div");
        row.className = "user-row";

        const identity = document.createElement("div");
        identity.className = "user-identity";
        const name = document.createElement("strong");
        name.textContent = user.display_name;
        const details = document.createElement("span");
        details.textContent = `${user.email} · 最近登录 ${accountTime(user.last_login_at)}`;
        identity.append(name, details);

        const role = document.createElement("span");
        role.className = `role-label${user.role === "admin" ? " admin" : ""}`;
        role.textContent = user.role === "admin" ? "管理员" : "普通用户";

        const toggle = document.createElement("label");
        toggle.className = "user-toggle";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = user.is_active;
        checkbox.disabled = user.id === currentUser.id;
        const label = document.createElement("span");
        label.textContent = user.is_active ? "已启用" : "已停用";
        checkbox.addEventListener("change", async () => {
            checkbox.disabled = true;
            try {
                await api(`/api/admin/users/${encodeURIComponent(user.id)}`, {
                    method: "PATCH",
                    body: JSON.stringify({ is_active: checkbox.checked }),
                });
                await loadUsers();
                showToast(checkbox.checked ? "账号已启用" : "账号已停用");
            } catch (error) {
                checkbox.checked = !checkbox.checked;
                checkbox.disabled = false;
                showToast(error.message, true);
            }
        });
        toggle.append(checkbox, label);
        row.append(identity, role, toggle);
        elements.userList.append(row);
    });
}

async function loadUsers() {
    const result = await api("/api/admin/users");
    elements.registrationEnabled.checked = result.registration_enabled;
    renderUsers(result.users);
}

async function saveProfile(event) {
    event.preventDefault();
    try {
        const result = await api("/api/auth/profile", {
            method: "PUT",
            body: JSON.stringify({ display_name: elements.profileDisplayName.value.trim() }),
        });
        currentUser = result.user;
        renderCurrentUser();
        showToast("昵称已更新");
    } catch (error) { showToast(error.message, true); }
}

async function savePassword(event) {
    event.preventDefault();
    if (elements.newPassword.value !== elements.confirmNewPassword.value) {
        showToast("两次输入的新密码不一致", true);
        elements.confirmNewPassword.focus();
        return;
    }
    try {
        const session = await api("/api/auth/password", {
            method: "PUT",
            body: JSON.stringify({
                current_password: elements.currentPassword.value,
                new_password: elements.newPassword.value,
            }),
        });
        csrfToken = session.csrf_token;
        currentUser = session.user;
        elements.passwordForm.reset();
        showToast("密码已更新，其他会话已退出");
    } catch (error) { showToast(error.message, true); }
}

async function logout() {
    stopPolling();
    try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* clear local session */ }
    elements.accountDialog.close();
    showAuth();
}

function formatBytes(value) {
    if (!Number.isFinite(value) || value < 0) return "-";
    if (value < 1024) return `${value} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let size = value / 1024;
    let unit = units[0];
    for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i]; }
    return `${size >= 10 ? size.toFixed(1) : size.toFixed(2)} ${unit}`;
}

function formatTime(seconds) {
    return new Intl.DateTimeFormat("zh-CN", {
        year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(new Date(seconds * 1000));
}

function taskLabel(state) {
    return { pending: "等待中", processing: "下载中", success: "已完成", failed: "失败", skipped: "已存在", cancelled: "已取消" }[state] || state;
}

function enhancementLabel(state) {
    return { pending: "等待中", processing: "增强中", success: "已完成", partial: "部分完成", failed: "失败" }[state] || state;
}

function taskProgress(task) {
    const files = (currentState?.files || []).filter((item) => item.task_id === task.task_id);
    if (!files.length) return { percent: task.state === "success" ? 100 : 0, detail: "等待文件信息" };
    let completed = 0;
    let total = 0;
    let known = true;
    files.forEach((file) => {
        completed += file.completed_bytes || 0;
        if (file.total_bytes) total += file.total_bytes; else known = false;
    });
    const percent = task.state === "success" ? 100 : (known && total ? Math.min(100, completed / total * 100) : 0);
    return { percent, detail: known && total ? `${formatBytes(completed)} / ${formatBytes(total)}` : `${files.length} 个文件` };
}

function createIconButton(iconName, title, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "icon-button subtle";
    button.title = title;
    button.setAttribute("aria-label", title);
    button.innerHTML = `<i data-lucide="${iconName}"></i>`;
    button.addEventListener("click", onClick);
    return button;
}

function renderTasks() {
    const tasks = currentState?.tasks || [];
    elements.taskList.replaceChildren();
    const active = tasks.filter((task) => ["pending", "processing"].includes(task.state)).length;
    elements.taskSummary.textContent = tasks.length ? `${tasks.length} 个任务，${active} 个进行中` : "暂无任务";
    if (!tasks.length) {
        elements.taskList.innerHTML = '<div class="empty-state"><i data-lucide="inbox"></i><span>暂无下载任务</span></div>';
        refreshIcons();
        return;
    }
    [...tasks].reverse().forEach((task) => {
        const progress = taskProgress(task);
        const row = document.createElement("div");
        row.className = "task-row";

        const name = document.createElement("div");
        name.className = "task-name";
        const strong = document.createElement("strong");
        strong.textContent = task.display_text || task.url;
        strong.title = task.url;
        const source = document.createElement("span");
        source.textContent = task.source === "monitor" ? "剪贴板监听" : "页面提交";
        name.append(strong, source);

        const progressCell = document.createElement("div");
        progressCell.className = "task-progress";
        progressCell.innerHTML = `<div class="progress-track"><div class="progress-bar" style="width:${progress.percent}%"></div></div><span class="progress-meta">${progress.detail}</span>`;

        const state = document.createElement("span");
        state.className = `state-pill ${task.state}`;
        state.textContent = taskLabel(task.state);

        const cancel = createIconButton("x", "取消任务", async () => {
            try { await api(`/api/tasks/${encodeURIComponent(task.task_id)}`, { method: "DELETE" }); await refreshState(); }
            catch (error) { showToast(error.message, true); }
        });
        cancel.disabled = task.state !== "pending";
        row.append(name, progressCell, state, cancel);
        elements.taskList.append(row);
    });
    refreshIcons();
}

function filteredLibrary() {
    const query = elements.fileSearch.value.trim().toLocaleLowerCase();
    return query ? libraryItems.filter((item) => item.path.toLocaleLowerCase().includes(query)) : libraryItems;
}

function updateSelection() {
    const visible = filteredLibrary();
    const selectedVisible = visible.filter((item) => selectedFiles.has(item.path)).length;
    elements.selectAllFiles.checked = visible.length > 0 && selectedVisible === visible.length;
    elements.selectAllFiles.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
    elements.archiveButton.disabled = selectedFiles.size === 0;
    elements.archiveButton.lastChild.textContent = selectedFiles.size ? `打包下载 (${selectedFiles.size})` : "打包下载";
    const mediaCount = libraryItems.filter((item) => selectedFiles.has(item.path) && ENHANCEABLE_SUFFIXES.has(item.suffix)).length;
    const hasActiveEnhancement = enhancementTasks.some((task) => ["pending", "processing"].includes(task.state));
    elements.enhanceButton.disabled = mediaCount === 0 || hasActiveEnhancement;
    elements.enhanceButton.lastChild.textContent = mediaCount ? `清晰增强 2x (${mediaCount})` : "清晰增强 2x";
    const liveMedia = selectedLiveMedia();
    const hasActiveLivePhoto = livePhotoTasks.some((task) => ["pending", "processing"].includes(task.state));
    elements.livePhotoButton.disabled = selectedFiles.size !== 1 || liveMedia.length !== 1 || hasActiveLivePhoto;
    const aiImages = selectedAIImages();
    const usedCount = Math.min(aiImages.length, 4);
    elements.aiVisualCount.lastChild.textContent = aiImages.length > 4
        ? `视觉参考 ${usedCount}/${aiImages.length} 张`
        : `视觉参考 ${usedCount} 张`;
    elements.aiVisualCount.title = aiImages.length > 4 ? "每次生成使用列表中靠前的 4 张图片" : "";
}

function selectedAIImages() {
    return libraryItems.filter((item) => selectedFiles.has(item.path) && item.ai_compatible);
}

function selectedLiveMedia() {
    return libraryItems.filter((item) => selectedFiles.has(item.path) && item.live_convertible !== false && LIVE_PHOTO_SUFFIXES.has(item.suffix));
}

function previewableMedia() {
    return libraryItems.filter((item) => item.preview_url && ["image", "video"].includes(item.media_kind));
}

function resetMediaViewer() {
    elements.mediaViewerVideo.pause();
    elements.mediaViewerVideo.removeAttribute("src");
    elements.mediaViewerVideo.load();
    elements.mediaViewerVideo.hidden = true;
    elements.mediaViewerImage.removeAttribute("src");
    elements.mediaViewerImage.hidden = true;
    elements.mediaViewerImage.classList.remove("zoomed");
    elements.mediaStage.classList.remove("zoom-active");
    elements.mediaStage.scrollTo(0, 0);
}

function showMediaAt(index) {
    const media = previewableMedia();
    if (!media.length) return;
    currentMediaIndex = Math.max(0, Math.min(index, media.length - 1));
    const item = media[currentMediaIndex];
    resetMediaViewer();
    elements.mediaViewerTitle.textContent = item.name;
    elements.mediaViewerMeta.textContent = `${item.media_kind === "video" ? (item.is_live ? "实况视频" : "视频") : "图片"} · ${formatBytes(item.size)}`;
    elements.mediaViewerDownload.href = item.download_url;
    elements.mediaViewerDownload.download = item.name;
    elements.previousMediaButton.disabled = currentMediaIndex === 0;
    elements.nextMediaButton.disabled = currentMediaIndex === media.length - 1;
    if (item.media_kind === "video") {
        elements.mediaViewerVideo.src = item.preview_url;
        elements.mediaViewerVideo.hidden = false;
    } else {
        elements.mediaViewerImage.src = item.preview_url;
        elements.mediaViewerImage.alt = item.name;
        elements.mediaViewerImage.hidden = false;
    }
}

function openMediaViewer(item) {
    const index = previewableMedia().findIndex((entry) => entry.path === item.path);
    if (index < 0) return;
    showMediaAt(index);
    if (!elements.mediaViewerDialog.open) elements.mediaViewerDialog.showModal();
    refreshIcons();
}

function createMediaPreview(item) {
    const cell = document.createElement("td");
    cell.className = "preview-cell";
    if (!item.preview_url) {
        const placeholder = document.createElement("span");
        placeholder.className = "media-placeholder";
        placeholder.textContent = item.suffix.toUpperCase();
        cell.append(placeholder);
        return cell;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "media-thumbnail";
    button.title = `预览 ${item.name}`;
    button.setAttribute("aria-label", `预览 ${item.name}`);
    if (item.media_kind === "image") {
        const image = document.createElement("img");
        image.src = item.preview_url;
        image.alt = "";
        image.loading = "lazy";
        button.append(image);
    } else {
        const video = document.createElement("video");
        video.src = item.preview_url;
        video.preload = "metadata";
        video.muted = true;
        video.playsInline = true;
        button.append(video);
        const play = document.createElement("span");
        play.className = "thumbnail-play";
        play.innerHTML = '<i data-lucide="play"></i>';
        button.append(play);
    }
    if (item.is_live) {
        const live = document.createElement("span");
        live.className = "live-marker";
        live.textContent = "实况";
        button.append(live);
    }
    button.addEventListener("click", () => openMediaViewer(item));
    cell.append(button);
    return cell;
}

function renderEnhancements() {
    const task = enhancementTasks[0];
    elements.enhancementPanel.hidden = !task;
    if (!task) { updateSelection(); return; }
    const percent = task.total ? Math.round(task.completed / task.total * 100) : 0;
    elements.enhancementTitle.textContent = `清晰增强 · ${task.completed}/${task.total}`;
    if (task.current) elements.enhancementDetail.textContent = `正在处理 ${task.current}`;
    else if (task.state === "success") elements.enhancementDetail.textContent = `已生成 ${task.outputs.length} 个 2 倍增强副本`;
    else if (task.state === "partial") elements.enhancementDetail.textContent = `已生成 ${task.outputs.length} 个，${task.errors.length} 个失败`;
    else if (task.state === "failed") elements.enhancementDetail.textContent = task.errors[0]?.error || "处理失败";
    else elements.enhancementDetail.textContent = "任务即将开始";
    elements.enhancementProgress.style.width = `${percent}%`;
    elements.enhancementState.className = `state-pill ${task.state}`;
    elements.enhancementState.textContent = enhancementLabel(task.state);
    updateSelection();
    refreshIcons();
}

function renderLivePhotos() {
    const task = livePhotoTasks[0];
    elements.livePhotoPanel.hidden = !task;
    if (!task) { updateSelection(); return; }
    const sourceName = task.source.split("/").pop();
    elements.livePhotoTitle.textContent = task.source_kind === "image" ? "图片生成实况" : "视频裁剪实况";
    if (task.state === "success") elements.livePhotoDetail.textContent = `已生成 ${task.output.split("/").pop()}`;
    else if (task.state === "failed") elements.livePhotoDetail.textContent = task.error || "生成失败";
    else if (task.state === "processing") elements.livePhotoDetail.textContent = `正在处理 ${sourceName}`;
    else elements.livePhotoDetail.textContent = `${sourceName} 即将开始`;
    elements.livePhotoState.className = `state-pill ${task.state}`;
    elements.livePhotoState.textContent = enhancementLabel(task.state);
    updateSelection();
    refreshIcons();
}

function renderLibrary() {
    const visible = filteredLibrary();
    elements.fileList.replaceChildren();
    const table = elements.fileList.closest("table");
    table.hidden = visible.length === 0;
    elements.librarySummary.textContent = `${libraryItems.length} / ${currentState?.libraryTotal ?? libraryItems.length} 个文件`;
    visible.forEach((item) => {
        const row = document.createElement("tr");
        const selectCell = document.createElement("td");
        selectCell.className = "select-cell";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = selectedFiles.has(item.path);
        checkbox.setAttribute("aria-label", `选择 ${item.name}`);
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) selectedFiles.add(item.path); else selectedFiles.delete(item.path);
            updateSelection();
        });
        selectCell.append(checkbox);

        const preview = createMediaPreview(item);

        const name = document.createElement("td");
        const nameText = document.createElement("div");
        nameText.className = "file-name";
        nameText.textContent = item.name;
        nameText.title = item.path;
        name.append(nameText);

        const kind = document.createElement("td");
        kind.className = "file-kind";
        kind.textContent = item.suffix;
        const size = document.createElement("td");
        size.textContent = formatBytes(item.size);
        const time = document.createElement("td");
        time.textContent = formatTime(item.modified);
        const action = document.createElement("td");
        action.className = "action-cell";
        const link = document.createElement("a");
        link.className = "file-download";
        link.href = item.download_url;
        link.download = item.name;
        link.title = "下载文件";
        link.setAttribute("aria-label", `下载 ${item.name}`);
        link.innerHTML = '<i data-lucide="download"></i>';
        action.append(link);
        row.append(selectCell, preview, name, kind, size, time, action);
        elements.fileList.append(row);
    });
    updateSelection();
    refreshIcons();
}

async function refreshState() {
    try {
        currentState = await api("/api/state");
        elements.serviceStatus.className = "service-status online";
        elements.serviceStatus.querySelector("span").textContent = "服务正常";
        const settings = currentState.settings || {};
        elements.downloadRoot.textContent = `${settings.effective_work_path || ""}\\${settings.folder_name || "Download"}`;
        elements.cookieState.textContent = settings.cookie_configured ? "已配置" : "未配置";
        const liveEnabled = Boolean(settings.live_download);
        elements.livePhotoBadge.classList.toggle("off", !liveEnabled);
        elements.livePhotoBadge.lastChild.textContent = liveEnabled ? "实况图片已开启" : "实况图片未开启";
        if (!currentState.disclaimer_accepted && !elements.disclaimerDialog.open) elements.disclaimerDialog.showModal();
        renderTasks();
        const fingerprint = (currentState.tasks || []).map((task) => `${task.task_id}:${task.state}`).join("|");
        if (fingerprint !== previousTaskFingerprint && /success|skipped/.test(fingerprint)) await refreshLibrary();
        previousTaskFingerprint = fingerprint;
    } catch (error) {
        elements.serviceStatus.className = "service-status error";
        elements.serviceStatus.querySelector("span").textContent = "服务异常";
    }
}

async function refreshLibrary() {
    try {
        const result = await api("/api/library?limit=500");
        libraryItems = result.items;
        currentState = { ...(currentState || {}), libraryTotal: result.total };
        selectedFiles = new Set([...selectedFiles].filter((path) => libraryItems.some((item) => item.path === path)));
        renderLibrary();
    } catch (error) { showToast(error.message, true); }
}

async function refreshEnhancements() {
    try {
        const result = await api("/api/enhancements");
        enhancementTasks = result.tasks;
        const fingerprint = enhancementTasks.map((task) => `${task.task_id}:${task.state}:${task.completed}`).join("|");
        if (fingerprint !== previousEnhancementFingerprint && /success|partial/.test(fingerprint)) await refreshLibrary();
        previousEnhancementFingerprint = fingerprint;
        renderEnhancements();
    } catch (error) { showToast(error.message, true); }
}

async function refreshLivePhotos() {
    try {
        const result = await api("/api/live-photos");
        livePhotoTasks = result.tasks;
        const fingerprint = livePhotoTasks.map((task) => `${task.task_id}:${task.state}:${task.output}`).join("|");
        if (fingerprint !== previousLivePhotoFingerprint && /success/.test(fingerprint)) await refreshLibrary();
        previousLivePhotoFingerprint = fingerprint;
        renderLivePhotos();
    } catch (error) { showToast(error.message, true); }
}

async function pasteLink() {
    try {
        let content = "";
        if (navigator.clipboard?.readText) {
            try { content = await navigator.clipboard.readText(); } catch (_) { /* server fallback */ }
        }
        if (!content) content = (await api("/api/clipboard", { method: "POST" })).content;
        elements.urlInput.value = content || "";
        elements.urlInput.focus();
        if (!content) showToast("剪贴板中没有文本", true);
    } catch (error) { showToast(error.message, true); }
}

async function createDownload() {
    const content = elements.urlInput.value.trim();
    if (!content) { showToast("请先粘贴笔记链接", true); elements.urlInput.focus(); return; }
    elements.downloadButton.disabled = true;
    try {
        // The main input also accepts 1688 mobile share text for a seamless workflow.
        if (/1688\.com|阿里|1688/i.test(content)) {
            const result = await api("/api/1688/collect", {
                method: "POST",
                body: JSON.stringify({ urls: [content], limit: 100 }),
            });
            elements.alibabaUrls.value = content;
            renderAlibabaProducts(result.products || []);
            showToast(`1688 商品采集完成，共 ${result.total} 个`);
            elements.urlInput.value = "";
            return;
        }
        const result = await api("/api/tasks", { method: "POST", body: JSON.stringify({ content }) });
        showToast(`已创建 ${result.tasks.length} 个下载任务`);
        elements.urlInput.value = "";
        await refreshState();
    } catch (error) { showToast(error.message, true); }
    finally { elements.downloadButton.disabled = false; }
}

async function downloadArchive() {
    if (!selectedFiles.size) return;
    elements.archiveButton.disabled = true;
    try {
        const response = await fetch("/api/archive", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
            body: JSON.stringify({ paths: [...selectedFiles] }),
        });
        if (!response.ok) throw new Error((await response.json()).detail || "打包失败");
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = "xiaohongshu-download.zip";
        link.hidden = true;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) { showToast(error.message, true); }
    finally { updateSelection(); }
}

async function createEnhancement() {
    const paths = libraryItems.filter((item) => selectedFiles.has(item.path) && ENHANCEABLE_SUFFIXES.has(item.suffix)).map((item) => item.path);
    if (!paths.length) return;
    elements.enhanceButton.disabled = true;
    try {
        const result = await api("/api/enhancements", { method: "POST", body: JSON.stringify({ paths }) });
        showToast(`已提交 ${result.task.total} 个清晰增强文件`);
        selectedFiles.clear();
        renderLibrary();
        await refreshEnhancements();
    } catch (error) { showToast(error.message, true); }
    finally { updateSelection(); }
}

function syncLivePhotoControls() {
    const isVideo = livePhotoSource?.media_kind === "video";
    let start = Number(elements.liveStartRange.value) || 0;
    const sourceDuration = elements.livePhotoVideo.duration;
    if (isVideo && Number.isFinite(sourceDuration)) {
        const maxStart = Math.max(0, sourceDuration - 0.5);
        elements.liveStartRange.max = maxStart.toFixed(1);
        start = Math.min(start, maxStart);
        elements.liveStartRange.value = start.toFixed(1);
        const maxDuration = Math.max(0.5, Math.min(5, sourceDuration - start));
        elements.liveDurationRange.max = maxDuration.toFixed(1);
        if (Number(elements.liveDurationRange.value) > maxDuration) {
            elements.liveDurationRange.value = maxDuration.toFixed(1);
        }
    } else {
        elements.liveStartRange.max = "0";
        elements.liveDurationRange.max = "5";
    }
    elements.liveStartValue.textContent = `${start.toFixed(1)} 秒`;
    elements.liveDurationValue.textContent = `${Number(elements.liveDurationRange.value).toFixed(1)} 秒`;
}

function resetLivePhotoEditor() {
    elements.livePhotoVideo.pause();
    elements.livePhotoVideo.removeAttribute("src");
    elements.livePhotoVideo.load();
    elements.livePhotoVideo.hidden = true;
    elements.livePhotoImage.removeAttribute("src");
    elements.livePhotoImage.hidden = true;
    livePhotoSource = null;
}

function openLivePhotoEditor() {
    const source = selectedLiveMedia()[0];
    if (!source || selectedFiles.size !== 1) return;
    resetLivePhotoEditor();
    livePhotoSource = source;
    elements.livePhotoMeta.textContent = `${source.media_kind === "image" ? "图片" : "视频"} · ${source.name} · ${formatBytes(source.size)}`;
    elements.liveStartRange.value = "0";
    elements.liveDurationRange.value = "3";
    elements.liveStartField.hidden = source.media_kind !== "video";
    if (source.media_kind === "video") {
        elements.livePhotoVideo.src = source.preview_url;
        elements.livePhotoVideo.hidden = false;
    } else {
        elements.livePhotoImage.src = source.preview_url;
        elements.livePhotoImage.alt = source.name;
        elements.livePhotoImage.hidden = false;
    }
    syncLivePhotoControls();
    elements.livePhotoDialog.showModal();
    refreshIcons();
}

async function createLivePhoto(event) {
    event.preventDefault();
    if (!livePhotoSource) return;
    const sourceKind = livePhotoSource.media_kind;
    elements.createLivePhotoButton.disabled = true;
    try {
        const result = await api("/api/live-photos", {
            method: "POST",
            body: JSON.stringify({
                path: livePhotoSource.path,
                start: livePhotoSource.media_kind === "video" ? Number(elements.liveStartRange.value) : 0,
                duration: Number(elements.liveDurationRange.value),
            }),
        });
        elements.livePhotoDialog.close();
        selectedFiles.clear();
        renderLibrary();
        livePhotoTasks = [result.task, ...livePhotoTasks];
        renderLivePhotos();
        showToast(sourceKind === "video" ? "视频裁剪任务已提交" : "图片转实况任务已提交");
        await refreshLivePhotos();
    } catch (error) { showToast(error.message, true); }
    finally { elements.createLivePhotoButton.disabled = false; }
}

function renderAIConfig(config) {
    elements.aiBaseUrl.value = config.base_url || "";
    elements.aiModel.value = config.model || "";
    elements.aiImageModel.value = config.image_model || "gpt-image-2";
    elements.aiProtocols.forEach((input) => { input.checked = input.value === config.protocol; });
    elements.aiApiKey.value = "";
    elements.clearAIKey.checked = false;
    elements.clearAIKey.disabled = !config.api_key_configured;
    if (config.configured) {
        const imageModel = config.image_model ? ` · 图片 ${config.image_model}` : "";
        elements.aiConfigState.textContent = `已配置 · ${config.model}${imageModel}`;
        elements.aiGenerationState.textContent = `${config.model}${imageModel} · 可开始生成`;
    } else if (config.base_url || config.api_key_configured || config.model) {
        elements.aiConfigState.textContent = "配置未完整";
        elements.aiGenerationState.textContent = "AI 配置未完整";
    } else {
        elements.aiConfigState.textContent = "未配置";
        elements.aiGenerationState.textContent = "请先配置 AI 中转";
    }
}

function syncAIGenerationMode() {
    const createMode = [...elements.aiGenerationModes].some((input) => input.checked && input.value === "create");
    elements.aiImageOptions.hidden = !createMode;
    elements.generateAIButtonLabel.textContent = createMode ? "生成图文" : "生成内容";
}

function clearGeneratedImage() {
    elements.aiImageResult.hidden = true;
    elements.generatedImagePreview.removeAttribute("src");
    elements.generatedImagePreviewButton.dataset.path = "";
    elements.generatedImageLivePhoto.dataset.path = "";
    elements.generatedImageLivePhoto.disabled = true;
    elements.generatedImageDownload.href = "#";
    elements.generatedImageDownload.removeAttribute("download");
    elements.generatedImageMeta.textContent = "";
}

function renderGeneratedImage(item, model, size) {
    if (!item) {
        clearGeneratedImage();
        return;
    }
    const [width, height] = size.split("x").map(Number);
    elements.generatedImagePreviewButton.style.aspectRatio = `${width} / ${height}`;
    elements.generatedImagePreview.src = item.preview_url;
    elements.generatedImagePreviewButton.dataset.path = item.path;
    elements.generatedImageLivePhoto.dataset.path = item.path;
    elements.generatedImageLivePhoto.disabled = false;
    elements.generatedImageMeta.textContent = `${model} · ${formatBytes(item.size)}`;
    elements.generatedImageDownload.href = item.download_url;
    elements.generatedImageDownload.download = item.name;
    elements.aiImageResult.hidden = false;
}

async function loadAIConfig() {
    const config = await api("/api/ai/config");
    renderAIConfig(config);
    return config;
}

async function generateAIContent() {
    const sourceText = elements.aiSourceText.value.trim();
    const imagePaths = selectedAIImages().slice(0, 4).map((item) => item.path);
    if (!sourceText && !imagePaths.length) {
        showToast("请输入内容或选择参考图片", true);
        elements.aiSourceText.focus();
        return;
    }
    const mode = [...elements.aiGenerationModes].find((input) => input.checked)?.value || "rewrite";
    const generateImage = mode === "create";
    elements.generateAIButton.disabled = true;
    elements.copyAIOutputButton.disabled = true;
    clearGeneratedImage();
    elements.aiGenerationState.textContent = generateImage ? "正在生成文案和图片" : "正在生成内容";
    elements.aiOutput.placeholder = generateImage ? "AI 正在生成文案和图片..." : "AI 正在分析素材并生成内容...";
    try {
        const result = await api("/api/ai/generate", {
            method: "POST",
            body: JSON.stringify({
                mode,
                source_text: sourceText,
                instructions: elements.aiInstructions.value.trim(),
                image_paths: imagePaths,
                generate_image: generateImage,
                image_size: elements.aiImageSize.value,
                image_quality: elements.aiImageQuality.value,
            }),
        });
        elements.aiOutput.value = result.text;
        elements.copyAIOutputButton.disabled = !result.text;
        const imageDetail = result.images_used ? ` · ${result.images_used} 张参考图` : "";
        const generatedImage = result.generated_images?.[0];
        if (generatedImage) {
            renderGeneratedImage(generatedImage, result.image_model, elements.aiImageSize.value);
            await refreshLibrary();
            elements.aiGenerationState.textContent = `图文生成完成 · ${result.model}${imageDetail}`;
            showToast("AI 文案和图片已生成");
        } else if (result.image_error) {
            elements.aiGenerationState.textContent = `文案已生成 · 图片生成失败`;
            showToast(result.image_error, true);
        } else {
            elements.aiGenerationState.textContent = `生成完成 · ${result.model}${imageDetail}`;
            showToast("AI 内容已生成");
        }
    } catch (error) {
        elements.aiGenerationState.textContent = "生成失败";
        showToast(error.message, true);
    } finally {
        elements.aiOutput.placeholder = "AI 生成结果将在这里显示";
        elements.generateAIButton.disabled = false;
    }
}

async function copyAIOutput() {
    const content = elements.aiOutput.value;
    if (!content) return;
    try {
        await navigator.clipboard.writeText(content);
        showToast("生成结果已复制");
    } catch (_) {
        elements.aiOutput.readOnly = false;
        elements.aiOutput.select();
        const copied = document.execCommand("copy");
        elements.aiOutput.readOnly = true;
        if (!copied) throw new Error("复制失败，请手动选择文本");
        showToast("生成结果已复制");
    }
}

function renderAlibabaProducts(products) {
    elements.alibabaSummary.textContent = products.length ? `已采集 ${products.length} 个商品` : "暂无采集结果";
    if (!products.length) {
        elements.alibabaProducts.innerHTML = '<div class="empty-state"><i data-lucide="package-open"></i><span>暂无商品</span></div>';
        refreshIcons();
        return;
    }
    elements.alibabaProducts.innerHTML = products.map((item) => { const images = (item.images || []).map((url) => url.startsWith("http") ? url : `/api/1688/assets/${url.replaceAll("\\\\", "/")}`); return `<article class="alibaba-card">
        ${images.length ? `<div class="alibaba-gallery">${images.slice(0, 6).map((url) => `<img src="${escapeHtml(url)}" alt="" loading="lazy">`).join("")}</div>` : '<div class="alibaba-placeholder"><i data-lucide="image"></i></div>'}
        <div><h3>${escapeHtml(item.title || "未命名商品")}</h3><p>${escapeHtml(item.price ? `参考价 ${item.price}` : (item.shop || "1688 商品"))}</p><p class="alibaba-specs">${Object.entries(item.specs || {}).slice(0, 4).map(([k,v]) => `${escapeHtml(k)}：${escapeHtml(v)}`).join(" · ")}</p><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">查看源商品</a></div>
    </article>`; }).join("");
    refreshIcons();
}

async function loadAlibabaProducts() {
    const result = await api("/api/1688/products");
    renderAlibabaProducts(result.products || []);
}

async function collectAlibabaProducts() {
    const urls = elements.alibabaUrls.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
    elements.alibabaCollect.disabled = true;
    elements.alibabaSummary.textContent = "正在采集公开商品页面…";
    try {
        const result = await api("/api/1688/collect", { method: "POST", body: JSON.stringify({ urls, keyword: elements.alibabaKeyword.value, limit: 100 }) });
        renderAlibabaProducts(result.products || []);
        showToast(`1688 商品采集完成，共 ${result.total} 个`);
    } catch (error) { showToast(error.message, true); }
    finally { elements.alibabaCollect.disabled = false; }
}

async function persistAIConfig(closeDialog = true) {
    const result = await api("/api/ai/config", {
        method: "PUT",
        body: JSON.stringify({
            base_url: elements.aiBaseUrl.value,
            api_key: elements.aiApiKey.value,
            model: elements.aiModel.value,
            image_model: elements.aiImageModel.value,
            clear_api_key: elements.clearAIKey.checked,
            protocol: [...elements.aiProtocols].find((input) => input.checked)?.value || "responses",
        }),
    });
    renderAIConfig(result.config);
    if (closeDialog) elements.aiSettingsDialog.close();
    return result.config;
}

async function saveAIConfig(event) {
    event.preventDefault();
    elements.saveAIButton.disabled = true;
    try {
        await persistAIConfig();
        showToast("AI 中转配置已保存");
    } catch (error) { showToast(error.message, true); }
    finally { elements.saveAIButton.disabled = false; }
}

async function testAIConnection() {
    elements.testAIButton.disabled = true;
    elements.saveAIButton.disabled = true;
    elements.aiConfigState.textContent = "正在测试连接";
    try {
        await persistAIConfig(false);
        const result = await api("/api/ai/test", { method: "POST" });
        const modelStatus = result.model_available === false ? "，默认模型未在列表中" : "";
        const imageModelStatus = result.image_model_available === false ? "，图片模型未在列表中" : "";
        elements.aiConfigState.textContent = `连接成功 · ${result.latency_ms} ms`;
        showToast(`AI 中转连接成功，共 ${result.models_count} 个模型${modelStatus}${imageModelStatus}`);
    } catch (error) {
        elements.aiConfigState.textContent = "连接失败";
        showToast(error.message, true);
    } finally {
        elements.testAIButton.disabled = false;
        elements.saveAIButton.disabled = false;
    }
}

elements.authModeInputs.forEach((input) => input.addEventListener("change", renderAuthMode));
elements.authForm.addEventListener("submit", submitAuthentication);
elements.accountButton.addEventListener("click", () => {
    renderCurrentUser();
    elements.accountDialog.showModal();
});
elements.profileForm.addEventListener("submit", saveProfile);
elements.passwordForm.addEventListener("submit", savePassword);
elements.logoutButton.addEventListener("click", logout);
elements.adminUsersButton.addEventListener("click", async () => {
    elements.adminUsersDialog.showModal();
    try { await loadUsers(); } catch (error) { showToast(error.message, true); }
});
elements.registrationEnabled.addEventListener("change", async () => {
    elements.registrationEnabled.disabled = true;
    try {
        const result = await api("/api/admin/registration", {
            method: "PUT",
            body: JSON.stringify({ enabled: elements.registrationEnabled.checked }),
        });
        authStatus.registration_enabled = result.registration_enabled;
        showToast(result.registration_enabled ? "已开放用户注册" : "已关闭用户注册");
    } catch (error) {
        elements.registrationEnabled.checked = !elements.registrationEnabled.checked;
        showToast(error.message, true);
    } finally {
        elements.registrationEnabled.disabled = false;
    }
});
document.querySelectorAll(".dialog-close").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
});

elements.pasteButton.addEventListener("click", pasteLink);
elements.clearInputButton.addEventListener("click", () => { elements.urlInput.value = ""; elements.urlInput.focus(); });
elements.downloadButton.addEventListener("click", createDownload);
elements.urlInput.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") createDownload(); });
elements.clearTasksButton.addEventListener("click", async () => { try { await api("/api/tasks", { method: "DELETE" }); await refreshState(); } catch (error) { showToast(error.message, true); } });
elements.fileSearch.addEventListener("input", renderLibrary);
elements.refreshLibraryButton.addEventListener("click", refreshLibrary);
elements.alibabaCollect.addEventListener("click", collectAlibabaProducts);
elements.selectAllFiles.addEventListener("change", () => {
    filteredLibrary().forEach((item) => { if (elements.selectAllFiles.checked) selectedFiles.add(item.path); else selectedFiles.delete(item.path); });
    renderLibrary();
});
elements.enhanceButton.addEventListener("click", createEnhancement);
elements.livePhotoButton.addEventListener("click", openLivePhotoEditor);
elements.livePhotoForm.addEventListener("submit", createLivePhoto);
elements.livePhotoVideo.addEventListener("loadedmetadata", syncLivePhotoControls);
elements.liveStartRange.addEventListener("input", () => {
    syncLivePhotoControls();
    if (Number.isFinite(elements.livePhotoVideo.duration)) {
        elements.livePhotoVideo.currentTime = Number(elements.liveStartRange.value);
    }
});
elements.liveDurationRange.addEventListener("input", syncLivePhotoControls);
elements.livePhotoDialog.addEventListener("close", resetLivePhotoEditor);
elements.livePhotoDialog.addEventListener("click", (event) => {
    if (event.target === elements.livePhotoDialog) elements.livePhotoDialog.close();
});
elements.archiveButton.addEventListener("click", downloadArchive);
elements.aiGenerationModes.forEach((input) => input.addEventListener("change", syncAIGenerationMode));
elements.generateAIButton.addEventListener("click", generateAIContent);
elements.copyAIOutputButton.addEventListener("click", () => {
    copyAIOutput().catch((error) => showToast(error.message, true));
});
elements.clearAIOutputButton.addEventListener("click", () => {
    elements.aiOutput.value = "";
    elements.copyAIOutputButton.disabled = true;
    clearGeneratedImage();
    elements.aiOutput.focus();
});
elements.generatedImagePreviewButton.addEventListener("click", async () => {
    const path = elements.generatedImagePreviewButton.dataset.path;
    if (!path) return;
    await refreshLibrary();
    const item = libraryItems.find((entry) => entry.path === path);
    if (item) openMediaViewer(item);
});
elements.generatedImageLivePhoto.addEventListener("click", async () => {
    const path = elements.generatedImageLivePhoto.dataset.path;
    if (!path) return;
    await refreshLibrary();
    const item = libraryItems.find((entry) => entry.path === path);
    if (!item) return;
    selectedFiles = new Set([path]);
    renderLibrary();
    openLivePhotoEditor();
});
elements.openFolderButton.addEventListener("click", async () => { try { await api("/api/folder/open", { method: "POST" }); } catch (error) { showToast(error.message, true); } });
elements.aiSettingsButton.addEventListener("click", async () => {
    elements.aiSettingsDialog.showModal();
    try { await loadAIConfig(); } catch (error) { showToast(error.message, true); }
});
elements.aiSettingsForm.addEventListener("submit", saveAIConfig);
elements.testAIButton.addEventListener("click", testAIConnection);
elements.toggleAIKeyButton.addEventListener("click", () => {
    const showing = elements.aiApiKey.type === "text";
    elements.aiApiKey.type = showing ? "password" : "text";
    elements.toggleAIKeyButton.innerHTML = `<i data-lucide="${showing ? "eye" : "eye-off"}"></i>`;
    refreshIcons();
});
elements.previousMediaButton.addEventListener("click", () => showMediaAt(currentMediaIndex - 1));
elements.nextMediaButton.addEventListener("click", () => showMediaAt(currentMediaIndex + 1));
elements.closeMediaViewerButton.addEventListener("click", () => elements.mediaViewerDialog.close());
elements.mediaViewerImage.addEventListener("click", () => {
    const zoomed = elements.mediaViewerImage.classList.toggle("zoomed");
    elements.mediaStage.classList.toggle("zoom-active", zoomed);
    if (!zoomed) elements.mediaStage.scrollTo(0, 0);
});
elements.mediaViewerDialog.addEventListener("close", () => {
    resetMediaViewer();
    currentMediaIndex = -1;
});
elements.mediaViewerDialog.addEventListener("click", (event) => {
    if (event.target === elements.mediaViewerDialog) elements.mediaViewerDialog.close();
});
document.addEventListener("keydown", (event) => {
    if (!elements.mediaViewerDialog.open) return;
    if (event.key === "ArrowLeft" && !elements.previousMediaButton.disabled) showMediaAt(currentMediaIndex - 1);
    if (event.key === "ArrowRight" && !elements.nextMediaButton.disabled) showMediaAt(currentMediaIndex + 1);
});
elements.settingsButton.addEventListener("click", () => { elements.cookieInput.value = ""; elements.settingsDialog.showModal(); });
elements.cookieForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const result = await api("/api/settings/cookie", { method: "PUT", body: JSON.stringify({ cookie: elements.cookieInput.value }) });
        elements.cookieState.textContent = result.cookie_configured ? "已配置" : "未配置";
        elements.cookieInput.value = "";
        elements.settingsDialog.close();
        showToast("Cookie 设置已保存");
    } catch (error) { showToast(error.message, true); }
});
elements.acceptDisclaimerButton.addEventListener("click", async () => {
    elements.acceptDisclaimerButton.disabled = true;
    try { await api("/api/disclaimer/accept", { method: "POST" }); elements.disclaimerDialog.close(); await refreshState(); }
    catch (error) { showToast(error.message, true); }
    finally { elements.acceptDisclaimerButton.disabled = false; }
});

syncAIGenerationMode();
refreshIcons();
bootstrapAuthentication();
