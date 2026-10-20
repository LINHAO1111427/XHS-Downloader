const byId = (id) => document.getElementById(id);

const elements = {
    authView: byId("authView"),
    appView: byId("appView"),
    navItems: document.querySelectorAll("[data-route]"),
    pagePanels: document.querySelectorAll("[data-page]"),
    mobilePageTitle: byId("mobilePageTitle"),
    navTaskCount: byId("navTaskCount"),
    aiViewTabs: document.querySelectorAll("[data-ai-view]"),
    aiViewPanels: document.querySelectorAll("[data-ai-panel]"),
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
    remixButton: byId("remixButton"),
    dedupeButton: byId("dedupeButton"),
    slideshowDialog: byId("slideshowDialog"),
    slideshowSeconds: byId("slideshowSeconds"),
    slideshowMusic: byId("slideshowMusic"),
    createSlideshowButton: byId("createSlideshowButton"),
    archiveButton: byId("archiveButton"),
    deleteSelectedButton: byId("deleteSelectedButton"),
    refreshLibraryButton: byId("refreshLibraryButton"),
    alibabaUrls: byId("alibabaUrls"),
    alibabaKeyword: byId("alibabaKeyword"),
    alibabaCollect: byId("alibabaCollect"),
    alibabaProducts: byId("alibabaProducts"),
    alibabaSummary: byId("alibabaSummary"),
    alibabaErrors: byId("alibabaErrors"),
    xhsProductUrl: byId("xhsProductUrl"),
    xhsProductCollect: byId("xhsProductCollect"),
    xhsProducts: byId("xhsProducts"),
    xhsProductSummary: byId("xhsProductSummary"),
    xhsProductErrors: byId("xhsProductErrors"),
    copyViewerImage: byId("copyViewerImage"),
    optimizeViewerImage: byId("optimizeViewerImage"),
    productViewerPosition: byId("productViewerPosition"),
    openFolderButton: byId("openFolderButton"),
    livePhotoBadge: byId("livePhotoBadge"),
    aiGenerationState: byId("aiGenerationState"),
    aiVisualCount: byId("aiVisualCount"),
    aiCorpusStatus: byId("aiCorpusStatus"),
    billingButton: byId("billingButton"),
    aiUsageText: byId("aiUsageText"),
    aiUsageMeta: byId("aiUsageMeta"),
    aiSourceText: byId("aiSourceText"),
    aiSourceLabel: byId("aiSourceLabel"),
    aiInstructions: byId("aiInstructions"),
    aiGenerationModes: document.querySelectorAll('input[name="aiGenerationMode"]'),
    aiCopywritingMode: byId("aiCopywritingMode"),
    aiProductName: byId("aiProductName"),
    aiTargetAudience: byId("aiTargetAudience"),
    aiSellingPoints: byId("aiSellingPoints"),
    aiPainPoints: byId("aiPainPoints"),
    aiKeywords: byId("aiKeywords"),
    aiProductPurpose: byId("aiProductPurpose"),
    aiLockedTitle: byId("aiLockedTitle"),
    aiCoverDescription: byId("aiCoverDescription"),
    aiProhibitedClaims: byId("aiProhibitedClaims"),
    aiOwnPostConfirmed: byId("aiOwnPostConfirmed"),
    copyProductField: byId("copyProductField"),
    copyTargetField: byId("copyTargetField"),
    copySellingField: byId("copySellingField"),
    copyPainField: byId("copyPainField"),
    copyKeywordsField: byId("copyKeywordsField"),
    copyPurposeField: byId("copyPurposeField"),
    copyTitleField: byId("copyTitleField"),
    copyCoverField: byId("copyCoverField"),
    copyProhibitedField: byId("copyProhibitedField"),
    copyOwnPostField: byId("copyOwnPostField"),
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
    aiImageEditState: byId("aiImageEditState"),
    aiEditSelectionCount: byId("aiEditSelectionCount"),
    aiEditImagePicker: byId("aiEditImagePicker"),
    aiEditUploadButton: byId("aiEditUploadButton"),
    aiEditUploadInput: byId("aiEditUploadInput"),
    aiEditUploadLabel: byId("aiEditUploadLabel"),
    aiEditUploadHint: byId("aiEditUploadHint"),
    clearAIEditSelection: byId("clearAIEditSelection"),
    aiEditPrompt: byId("aiEditPrompt"),
    aiEditInstructions: byId("aiEditInstructions"),
    aiEditSize: byId("aiEditSize"),
    aiEditQuality: byId("aiEditQuality"),
    editAIImageButton: byId("editAIImageButton"),
    aiEditEmpty: byId("aiEditEmpty"),
    aiEditResult: byId("aiEditResult"),
    aiEditResultMeta: byId("aiEditResultMeta"),
    aiEditPreviewButton: byId("aiEditPreviewButton"),
    aiEditPreview: byId("aiEditPreview"),
    aiEditDownload: byId("aiEditDownload"),
    reuseAIEditResult: byId("reuseAIEditResult"),
    historySearch: byId("historySearch"),
    refreshHistoryButton: byId("refreshHistoryButton"),
    historySummary: byId("historySummary"),
    historyList: byId("historyList"),
    historyLoadMore: byId("historyLoadMore"),
    historyEmpty: byId("historyEmpty"),
    historyDetail: byId("historyDetail"),
    historyDetailKind: byId("historyDetailKind"),
    historyDetailTitle: byId("historyDetailTitle"),
    historyDetailMeta: byId("historyDetailMeta"),
    historyFacts: byId("historyFacts"),
    historyImages: byId("historyImages"),
    historyOutput: byId("historyOutput"),
    historySourceSection: byId("historySourceSection"),
    historySource: byId("historySource"),
    historyFeedback: byId("historyFeedback"),
    reuseHistoryButton: byId("reuseHistoryButton"),
    copyHistoryButton: byId("copyHistoryButton"),
    deleteHistoryButton: byId("deleteHistoryButton"),
    corpusSearch: byId("corpusSearch"),
    refreshCorpusButton: byId("refreshCorpusButton"),
    corpusSummary: byId("corpusSummary"),
    corpusList: byId("corpusList"),
    corpusLoadMore: byId("corpusLoadMore"),
    corpusEmpty: byId("corpusEmpty"),
    corpusDetail: byId("corpusDetail"),
    corpusDetailTitle: byId("corpusDetailTitle"),
    corpusDetailMeta: byId("corpusDetailMeta"),
    corpusFacts: byId("corpusFacts"),
    corpusGallery: byId("corpusGallery"),
    corpusContent: byId("corpusContent"),
    corpusLinks: byId("corpusLinks"),
    useCorpusButton: byId("useCorpusButton"),
    generationFeedback: byId("generationFeedback"),
    generationRating: byId("generationRating"),
    generationFeedbackText: byId("generationFeedbackText"),
    reusableLesson: byId("reusableLesson"),
    knowledgeUsage: byId("knowledgeUsage"),
    saveGenerationFeedbackButton: byId("saveGenerationFeedback"),
    aiSettingsButton: byId("aiSettingsButton"),
    knowledgeButton: byId("knowledgeButton"),
    knowledgeDialog: byId("knowledgeDialog"),
    knowledgeSummary: byId("knowledgeSummary"),
    knowledgeForm: byId("knowledgeForm"),
    knowledgeKind: byId("knowledgeKind"),
    knowledgePriority: byId("knowledgePriority"),
    knowledgeActive: byId("knowledgeActive"),
    knowledgeTitle: byId("knowledgeTitle"),
    knowledgeTags: byId("knowledgeTags"),
    knowledgeContent: byId("knowledgeContent"),
    resetKnowledgeForm: byId("resetKnowledgeForm"),
    saveKnowledgeEntry: byId("saveKnowledgeEntry"),
    knowledgeSearch: byId("knowledgeSearch"),
    knowledgeFilter: byId("knowledgeFilter"),
    knowledgeList: byId("knowledgeList"),
    adminUsersButton: byId("adminUsersButton"),
    adminUsersDialog: byId("adminUsersDialog"),
    userSummary: byId("userSummary"),
    registrationEnabled: byId("registrationEnabled"),
    userList: byId("userList"),
    createUserForm: byId("createUserForm"),
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
    billingDialog: byId("billingDialog"),
    billingSummary: byId("billingSummary"),
    billingFreeRemaining: byId("billingFreeRemaining"),
    billingPaidCredits: byId("billingPaidCredits"),
    billingUsageDate: byId("billingUsageDate"),
    billingPlans: byId("billingPlans"),
    aiSettingsForm: byId("aiSettingsForm"),
    aiConfigState: byId("aiConfigState"),
    aiBaseUrl: byId("aiBaseUrl"),
    aiApiKey: byId("aiApiKey"),
    clearAIKey: byId("clearAIKey"),
    aiModel: byId("aiModel"),
    aiImageBaseUrl: byId("aiImageBaseUrl"),
    aiImageModel: byId("aiImageModel"),
    aiProtocols: document.querySelectorAll('input[name="aiProtocol"]'),
    toggleAIKeyButton: byId("toggleAIKeyButton"),
    testAIButton: byId("testAIButton"),
    saveAIButton: byId("saveAIButton"),
    settingsButton: byId("settingsButton"),
    rewriteExportSettings: byId("rewriteExportSettings"),
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
    liveMotionModeField: byId("liveMotionModeField"),
    liveMotionMode: byId("liveMotionMode"),
    liveMotionPromptField: byId("liveMotionPromptField"),
    liveMotionPrompt: byId("liveMotionPrompt"),
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

if (!elements.slideshowButton) {
    elements.slideshowButton = document.createElement("button");
    elements.slideshowButton.className = "button secondary";
    elements.slideshowButton.id = "slideshowButton";
    elements.slideshowButton.type = "button";
    elements.slideshowButton.disabled = true;
    elements.slideshowButton.title = "将选中图片制作成视频";
    elements.slideshowButton.innerHTML = '<i data-lucide="film"></i>图片成片';
    elements.remixButton.parentElement.insertBefore(elements.slideshowButton, elements.remixButton);
}
if (!elements.batchEditAIImageButton) {
    elements.batchEditAIImageButton = document.createElement("button");
    elements.batchEditAIImageButton.className = "button secondary";
    elements.batchEditAIImageButton.id = "batchEditAIImageButton";
    elements.batchEditAIImageButton.type = "button";
    elements.batchEditAIImageButton.disabled = true;
    elements.batchEditAIImageButton.title = "逐一优化选中的图片";
    elements.batchEditAIImageButton.innerHTML = '<i data-lucide="images"></i>批量优化';
    elements.editAIImageButton.parentElement.insertBefore(elements.batchEditAIImageButton, elements.editAIImageButton);
}
if (!elements.nineGridButton) {
    elements.nineGridButton = document.createElement("button");
    elements.nineGridButton.className = "button secondary";
    elements.nineGridButton.id = "nineGridButton";
    elements.nineGridButton.type = "button";
    elements.nineGridButton.disabled = true;
    elements.nineGridButton.title = "\u9009\u62e9 9 \u5f20\u56fe\u7247\u540e\u81ea\u52a8\u5408\u6210\u4e5d\u5bab\u683c";
    elements.nineGridButton.innerHTML = '<i data-lucide="grid-3x3"></i>\u751f\u6210\u4e5d\u5bab\u683c';
    elements.editAIImageButton.parentElement.insertBefore(elements.nineGridButton, elements.editAIImageButton);
}
if (elements.deleteSelectedButton && !elements.deleteSelectedButton.closest(".library-actions")) {
    document.querySelector(".library-actions")?.append(elements.deleteSelectedButton);
}
if (elements.livePhotoButton && !elements.livePhotoButton.closest(".library-actions")) {
    document.querySelector(".library-actions")?.append(elements.livePhotoButton);
}


const ENHANCEABLE_SUFFIXES = new Set(["jpeg", "jpg", "png", "webp", "m4v", "mov", "mp4"]);
const LIVE_PHOTO_SUFFIXES = new Set(["jpeg", "jpg", "png", "webp", "m4v", "mov", "mp4"]);
let currentState = null;
let libraryItems = [];
let enhancementTasks = [];
let remixTasks = [];
let livePhotoTasks = [];
let selectedFiles = new Set();
let toastTimer = null;
let previousTaskFingerprint = "";
let previousEnhancementFingerprint = "";
let previousRemixFingerprint = "";
let previousLivePhotoFingerprint = "";
let currentMediaIndex = -1;
let viewerItems = [];
let libraryFingerprint = "";
let tasksFingerprint = "";
let alibabaJobId = "";
let xhsProductJobId = "";
const productRecords = { "1688": [], xhs: [] };
let alibabaJobFingerprint = "";
const pendingReads = new Map();
let livePhotoSource = null;
let currentUser = null;
let serverMode = false;
let csrfToken = "";
let authStatus = { needs_setup: false, registration_enabled: true };
let pollTimers = [];
let authGeneration = 0;
let knowledgeEntries = [];
let editingKnowledgeId = "";
let currentGenerationRunId = "";
let knowledgeSearchTimer = null;
let aiImageConfigured = false;
let aiImageModelName = "";
let aiImageEditing = false;
let aiEditUploading = false;
let aiEditSelectedFiles = new Set();
let historyItems = [];
let historyTotal = 0;
let selectedHistory = null;
let corpusItems = [];
let corpusTotal = 0;
let selectedCorpus = null;
let historySearchTimer = null;
let corpusSearchTimer = null;
let historyLoaded = false;
let historyLoading = false;
let corpusLoaded = false;
let corpusLoading = false;
let billingUsage = null;
let billingPlans = [];

function refreshIcons() {
    if (!window.lucide || !document.querySelector("[data-lucide]")) return;
    window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
    document.querySelectorAll("svg[data-lucide]").forEach((icon) => icon.removeAttribute("data-lucide"));
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
}

const pageTitles = { download: "下载", operations: "小红书运营", products: "商品素材", viral: "低粉爆款", collect: "采集", ai: "AI 创作" };

function currentRoute() {
    const [page, view] = window.location.hash.replace(/^#/, "").split("/");
    const validAIViews = new Set(["copy", "image", "history", "corpus"]);
    return {
        page: Object.hasOwn(pageTitles, page) ? page : "download",
        aiView: validAIViews.has(view) ? view : "copy",
        productSource: ["xhs", "listing"].includes(view) ? view : "1688",
    };
}

function activateAIView(view) {
    const selected = new Set(["copy", "image", "history", "corpus"]).has(view) ? view : "copy";
    elements.aiViewTabs.forEach((button) => {
        const active = button.dataset.aiView === selected;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
    });
    elements.aiViewPanels.forEach((panel) => {
        const active = panel.dataset.aiPanel === selected;
        panel.hidden = !active;
        panel.classList.toggle("active", active);
    });
    if (selected === "image") renderAIEditPicker();
    if (selected === "history" && currentUser && !historyLoaded && !historyLoading) {
        loadHistory().catch((error) => showToast(error.message, true));
    }
    if (selected === "corpus" && currentUser && !corpusLoaded && !corpusLoading) {
        loadCorpus().catch((error) => showToast(error.message, true));
    }
}

function activateRoute() {
    const route = currentRoute();
    elements.navItems.forEach((button) => {
        const active = button.dataset.route === route.page;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    });
    elements.pagePanels.forEach((panel) => {
        const active = panel.dataset.page === route.page;
        panel.hidden = !active;
        panel.classList.toggle("active", active);
    });
    elements.mobilePageTitle.textContent = pageTitles[route.page];
    activateAIView(route.aiView);
    document.querySelectorAll("[data-product-tab]").forEach((tab) => {
        const active = tab.dataset.productTab === route.productSource;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll("[data-product-panel]").forEach((panel) => { panel.hidden = panel.dataset.productPanel !== route.productSource; });
    document.querySelector(".workspace-body")?.scrollTo({ top: 0, behavior: "instant" });
}

function navigateTo(page, aiView = "copy") {
    const nextHash = page === "ai" && aiView !== "copy" ? `#ai/${aiView}` : `#${page}`;
    if (window.location.hash === nextHash) activateRoute();
    else window.location.hash = nextHash;
}

class APIError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

const apiFieldLabels = {
    body: "请求内容",
    mode: "生成模式",
    copywriting_mode: "文案策略",
    source_text: "对标笔记正文",
    instructions: "补充要求",
    product_name: "产品或主题",
    target_audience: "目标人群",
    selling_points: "真实卖点与产品资料",
    pain_points: "用户痛点或场景",
    keywords: "搜索关键词",
    product_purpose: "产品用途或作用",
    cover_description: "已定封面",
    locked_title: "已定标题",
    prohibited_claims: "禁用表述",
    image_paths: "参考图片",
    image_size: "图片比例",
    image_quality: "图片质量",
    prompt: "修改目标",
};

function validationIssueText(issue) {
    if (!issue || typeof issue !== "object") return String(issue || "");
    const location = Array.isArray(issue.loc) ? issue.loc.filter((part) => part !== "body") : [];
    const field = apiFieldLabels[location[0]] || location.join(".") || "请求内容";
    const maximum = issue.ctx?.max_length;
    if (issue.type === "missing") return `请填写${field}`;
    if (issue.type === "string_too_long" && maximum) return `${field}不能超过 ${maximum} 个字符`;
    if (issue.type === "too_long" && maximum) return `${field}不能超过 ${maximum} 项`;
    if (issue.type === "string_too_short") return `请填写${field}`;
    if (issue.type === "literal_error") return `${field}的选项无效，请重新选择`;
    return issue.msg ? `${field}：${issue.msg}` : field;
}

function apiErrorText(payload, fallback) {
    const detail = payload?.detail ?? payload;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
        const messages = detail.map(validationIssueText).filter(Boolean);
        return messages.length ? messages.join("；") : fallback;
    }
    if (detail && typeof detail === "object") {
        if (typeof detail.message === "string") return detail.message;
        try { return JSON.stringify(detail); } catch (_) { return fallback; }
    }
    return fallback;
}

function api(path, options = {}) {
    const key = `${authGeneration}:${path}`;
    const read = (options.method || "GET").toUpperCase() === "GET";
    if (read && pendingReads.has(key)) return pendingReads.get(key);
    const request = requestAPI(path, options);
    if (!read) return request;
    const tracked = request.finally(() => pendingReads.delete(key));
    pendingReads.set(key, tracked);
    return tracked;
}

const pendingMutationKeys = new Map();

async function requestAPI(path, options = {}) {
    const requestGeneration = authGeneration;
    const method = (options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    const hasContentType = Object.keys(headers).some((name) => name.toLowerCase() === "content-type");
    if (options.body !== undefined && !hasContentType) headers["Content-Type"] = "application/json";
    if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method) && csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
    }
    // Keep the same key after a lost response. A manual retry can retrieve the
    // persisted result instead of buying another generation.
    const accounted = method === "POST" && ["/api/ai/generate", "/api/ai/images/edit", "/api/ai/images/edit/batch", "/api/billing/orders", "/api/admin/billing/grant"].includes(path);
    const mutationKey = accounted ? `${currentUser?.id || requestGeneration}:${path}:${options.body || ""}` : "";
    let mutationStorageKey = "";
    const clearMutationKey = () => {
        pendingMutationKeys.delete(mutationKey);
        try { if (mutationStorageKey) sessionStorage.removeItem(mutationStorageKey); } catch (_) { /* Storage may be disabled. */ }
    };
    if (accounted && !Object.keys(headers).some((name) => name.toLowerCase() === "idempotency-key")) {
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(mutationKey));
        mutationStorageKey = `xhs-pending:${Array.from(new Uint8Array(digest), (n) => n.toString(16).padStart(2, "0")).join("")}`;
        if (!pendingMutationKeys.has(mutationKey)) {
            let persisted = null;
            try { persisted = sessionStorage.getItem(mutationStorageKey); } catch (_) { /* Use the in-memory key. */ }
            pendingMutationKeys.set(mutationKey, persisted || crypto.randomUUID());
        }
        try { sessionStorage.setItem(mutationStorageKey, pendingMutationKeys.get(mutationKey)); } catch (_) { /* Use the in-memory key. */ }
        headers["Idempotency-Key"] = pendingMutationKeys.get(mutationKey);
    }
    const response = await fetch(path, {
        ...options,
        credentials: "same-origin",
        signal: options.signal || AbortSignal.timeout(method === "GET" ? 15000 : 300000),
        headers,
    });
    if (!response.ok) {
        let message = `请求失败 (${response.status})`;
        try {
            const errorPayload = await response.json();
            message = apiErrorText(errorPayload, message);
            if (errorPayload.code === "request_interrupted") clearMutationKey();
        } catch (_) { /* no-op */ }
        if (accounted && response.status !== 429 && response.status !== 409) clearMutationKey();
        if (response.status === 401 && !path.startsWith("/api/auth/") && requestGeneration === authGeneration) showAuth();
        throw new APIError(message, response.status);
    }
    const payload = response.status === 204 ? null : await response.json();
    if (accounted) clearMutationKey();
    return payload;
}

function showToast(message, error = false) {
    clearTimeout(toastTimer);
    elements.toast.textContent = typeof message === "string" ? message : apiErrorText(message, "操作失败");
    elements.toast.className = `toast show${error ? " error" : ""}`;
    toastTimer = setTimeout(() => { elements.toast.className = "toast"; }, 3200);
}

function startAIProgressTimer(element, label) {
    const startedAt = Date.now();
    const update = () => { element.textContent = `${label} · 已等待 ${Math.floor((Date.now() - startedAt) / 1000)} 秒`; };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
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

function pollingPaused() {
    return document.hidden || Boolean(document.querySelector("dialog[open]"));
}

function poll(action, interval) {
    let running = false;
    const generation = authGeneration;
    return setInterval(async () => {
        if (running || pollingPaused() || !currentUser || generation !== authGeneration) return;
        running = true;
        try { await action(); } catch (_) { /* Action renders its own status. */ }
        finally { running = false; }
    }, interval);
}

function stopPolling() {
    pollTimers.forEach((timer) => clearInterval(timer));
    pollTimers = [];
}

function showAuth(message = "") {
    authGeneration += 1;
    stopPolling();
    window.viralWorkspace?.stop();
    window.discoveryWorkspace?.stop();
    window.operationWorkspace?.stop();
    currentUser = null;
    window.commerceWorkspace?.stop();
    csrfToken = "";
    alibabaJobId = "";
    xhsProductJobId = "";
    libraryFingerprint = "";
    tasksFingerprint = "";
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    historyItems = [];
    historyTotal = 0;
    selectedHistory = null;
    historyLoaded = false;
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
    elements.knowledgeButton.hidden = !admin;
    elements.settingsButton.hidden = !admin && !serverMode;
    elements.rewriteExportSettings.hidden = !admin || serverMode;
    elements.openFolderButton.hidden = !admin || serverMode;
}

async function enterWorkspace(session) {
    authGeneration += 1;
    currentUser = session.user;
    serverMode = Boolean(session.server_mode);
    csrfToken = session.csrf_token;
    historyItems = [];
    historyTotal = 0;
    selectedHistory = null;
    historyLoaded = false;
    corpusLoaded = false;
    elements.authView.hidden = true;
    elements.appView.hidden = false;
    renderCurrentUser();
    activateRoute();
    refreshIcons();
    stopPolling();
    try {
        await Promise.all([refreshState(), refreshLibrary(), refreshEnhancements(), refreshRemixTasks(), refreshLivePhotos(), loadAIConfig(), refreshCorpusStatus(), loadBilling(), loadAlibabaProducts(), loadXhsProducts(), window.commerceWorkspace?.reload(), window.viralWorkspace?.start(), window.discoveryWorkspace?.start(), window.operationWorkspace?.start()]);
    } catch (error) {
        if (error.status !== 401) showToast(error.message, true);
    }
    if (!currentUser) return;
    pollTimers = [
        poll(refreshState, 2000),
        poll(refreshEnhancements, 3000),
        poll(refreshRemixTasks, 3000),
        poll(refreshLivePhotos, 3000),
        poll(refreshLibrary, 10000),
        poll(refreshAlibabaJob, 2000),
        poll(refreshXhsProductJob, 2000),
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
    if (result.max_users) {
        const count = result.users.filter((user) => user.role === "user").length;
        elements.userSummary.textContent = `试用账号 ${count} / ${result.max_users} · 管理员单独保留`;
    }
}

elements.createUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = elements.createUserForm.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
        const values = Object.fromEntries(new FormData(elements.createUserForm));
        await api("/api/admin/users", { method: "POST", body: JSON.stringify(values) });
        elements.createUserForm.reset();
        await loadUsers();
        showToast("账号已开通，请用户登录后修改密码");
    } catch (error) {
        showToast(error.message, true);
    } finally {
        button.disabled = false;
    }
});

function formatCredits(value) {
    return Number(value || 0).toLocaleString("zh-CN");
}

function renderBillingUsage(usage) {
    billingUsage = usage;
    const free = usage.unlimited ? "无限" : formatCredits(usage.free_remaining);
    const paid = formatCredits(usage.paid_credits);
    elements.aiUsageText.textContent = usage.unlimited ? "超级管理员 · 无限点数" : `今日还可用 ${free} 点`;
    elements.aiUsageMeta.textContent = usage.unlimited ? "文案、生图和图片修改不扣除点数" : `付费点数 ${paid} · 文本 ${usage.costs.text} 点 · 图片 ${usage.costs.image} 点`;
    elements.billingFreeRemaining.textContent = free;
    elements.billingPaidCredits.textContent = paid;
    elements.billingUsageDate.textContent = usage.usage_date;
}

function renderBillingPlans(plans) {
    billingPlans = plans;
    elements.billingPlans.replaceChildren();
    plans.filter((plan) => plan.id !== "free").forEach((plan, index) => {
        const card = document.createElement("article");
        card.className = `billing-plan${index === 1 ? " featured" : ""}`;
        const heading = document.createElement("div");
        heading.className = "billing-plan-heading";
        const title = document.createElement("strong");
        title.textContent = plan.name;
        const price = document.createElement("b");
        price.innerHTML = `<small>¥</small>${plan.price}`;
        heading.append(title, price);
        const credits = document.createElement("p");
        credits.textContent = `${formatCredits(plan.credits)} 点`;
        const detail = document.createElement("span");
        detail.textContent = plan.description;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button secondary billing-order-button";
        button.disabled = true;
        button.title = "等待管理员配置支付渠道";
        button.innerHTML = '<i data-lucide="lock-keyhole"></i><span>支付渠道待配置</span>';
        card.append(heading, credits, detail, button);
        elements.billingPlans.append(card);
    });
    refreshIcons();
}

async function loadBilling() {
    const [usage, plans] = await Promise.all([
        api("/api/billing/usage"),
        api("/api/billing/plans"),
    ]);
    renderBillingUsage(usage);
    renderBillingPlans(plans.plans);
}

const knowledgeKindLabels = { general: "通用", note: "笔记", image: "图片" };

function knowledgePayload(entry = null) {
    if (entry) {
        return {
            kind: entry.kind,
            title: entry.title,
            content: entry.content,
            tags: entry.tags,
            priority: entry.priority,
            active: entry.active,
        };
    }
    return {
        kind: elements.knowledgeKind.value,
        title: elements.knowledgeTitle.value.trim(),
        content: elements.knowledgeContent.value.trim(),
        tags: elements.knowledgeTags.value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean),
        priority: Number(elements.knowledgePriority.value),
        active: elements.knowledgeActive.checked,
    };
}

function resetKnowledgeEditor() {
    editingKnowledgeId = "";
    elements.knowledgeForm.reset();
    elements.knowledgeKind.value = "general";
    elements.knowledgePriority.value = "50";
    elements.knowledgeActive.checked = true;
    elements.saveKnowledgeEntry.lastElementChild.textContent = "保存条目";
}

function editKnowledgeEntry(entry) {
    editingKnowledgeId = entry.id;
    elements.knowledgeKind.value = entry.kind;
    elements.knowledgePriority.value = String(entry.priority);
    elements.knowledgeActive.checked = entry.active;
    elements.knowledgeTitle.value = entry.title;
    elements.knowledgeTags.value = entry.tags.join("，");
    elements.knowledgeContent.value = entry.content;
    elements.saveKnowledgeEntry.lastElementChild.textContent = "更新条目";
    elements.knowledgeTitle.focus();
}

function renderKnowledge(result) {
    knowledgeEntries = result.entries;
    const stats = result.stats;
    elements.knowledgeSummary.textContent = `${stats.active_entries}/${stats.entries} 条启用 · 已用于 ${stats.uses} 次生成 · ${stats.rated_runs} 次反馈`;
    elements.knowledgeList.replaceChildren();
    if (!knowledgeEntries.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.innerHTML = '<i data-lucide="book-dashed"></i><span>没有匹配的知识条目</span>';
        elements.knowledgeList.append(empty);
        refreshIcons();
        return;
    }
    knowledgeEntries.forEach((entry) => {
        const row = document.createElement("div");
        row.className = "knowledge-row";
        const main = document.createElement("div");
        main.className = "knowledge-main";
        const titleLine = document.createElement("div");
        titleLine.className = "knowledge-title-line";
        const title = document.createElement("strong");
        title.textContent = entry.title;
        const kind = document.createElement("span");
        kind.className = `knowledge-badge ${entry.kind}`;
        kind.textContent = knowledgeKindLabels[entry.kind];
        titleLine.append(title, kind);
        if (!entry.active) {
            const off = document.createElement("span");
            off.className = "knowledge-badge off";
            off.textContent = "未启用";
            titleLine.append(off);
        }
        const content = document.createElement("p");
        content.textContent = entry.content.length > 240 ? `${entry.content.slice(0, 240)}…` : entry.content;
        const meta = document.createElement("div");
        meta.className = "knowledge-meta";
        const tags = entry.tags.length ? ` · ${entry.tags.join(" / ")}` : "";
        meta.textContent = `优先级 ${entry.priority} · 使用 ${entry.use_count} 次${tags}`;
        main.append(titleLine, content, meta);

        const actions = document.createElement("div");
        actions.className = "knowledge-actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "icon-button subtle";
        edit.title = "编辑知识";
        edit.setAttribute("aria-label", "编辑知识");
        edit.innerHTML = '<i data-lucide="pencil"></i>';
        edit.addEventListener("click", () => editKnowledgeEntry(entry));
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "icon-button subtle";
        toggle.title = entry.active ? "停用知识" : "启用知识";
        toggle.setAttribute("aria-label", toggle.title);
        toggle.innerHTML = `<i data-lucide="${entry.active ? "pause" : "play"}"></i>`;
        toggle.addEventListener("click", async () => {
            try {
                await api(`/api/knowledge/${encodeURIComponent(entry.id)}`, {
                    method: "PUT",
                    body: JSON.stringify({ ...knowledgePayload(entry), active: !entry.active }),
                });
                await loadKnowledge();
            } catch (error) { showToast(error.message, true); }
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "icon-button subtle";
        remove.title = "删除知识";
        remove.setAttribute("aria-label", "删除知识");
        remove.innerHTML = '<i data-lucide="trash-2"></i>';
        remove.addEventListener("click", async () => {
            if (!window.confirm(`确认删除“${entry.title}”？`)) return;
            try {
                await api(`/api/knowledge/${encodeURIComponent(entry.id)}`, { method: "DELETE" });
                if (editingKnowledgeId === entry.id) resetKnowledgeEditor();
                await loadKnowledge();
                showToast("知识条目已删除");
            } catch (error) { showToast(error.message, true); }
        });
        actions.append(edit, toggle, remove);
        row.append(main, actions);
        elements.knowledgeList.append(row);
    });
    refreshIcons();
}

async function loadKnowledge() {
    const params = new URLSearchParams();
    const query = elements.knowledgeSearch.value.trim();
    if (query) params.set("query", query);
    if (elements.knowledgeFilter.value) params.set("kind", elements.knowledgeFilter.value);
    const suffix = params.toString() ? `?${params}` : "";
    const result = await api(`/api/knowledge${suffix}`);
    renderKnowledge(result);
    return result;
}

async function saveKnowledge(event) {
    event.preventDefault();
    elements.saveKnowledgeEntry.disabled = true;
    try {
        const path = editingKnowledgeId ? `/api/knowledge/${encodeURIComponent(editingKnowledgeId)}` : "/api/knowledge";
        const method = editingKnowledgeId ? "PUT" : "POST";
        await api(path, { method, body: JSON.stringify(knowledgePayload()) });
        showToast(editingKnowledgeId ? "知识条目已更新" : "知识条目已创建");
        resetKnowledgeEditor();
        await loadKnowledge();
    } catch (error) { showToast(error.message, true); }
    finally { elements.saveKnowledgeEntry.disabled = false; }
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
    if (task.error) return { percent: 0, detail: task.error };
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
    const fingerprint = JSON.stringify([tasks, currentState?.files]);
    if (fingerprint === tasksFingerprint) return;
    tasksFingerprint = fingerprint;
    elements.taskList.replaceChildren();
    const active = tasks.filter((task) => ["pending", "processing"].includes(task.state)).length;
    elements.taskSummary.textContent = tasks.length ? `${tasks.length} 个任务，${active} 个进行中` : "暂无任务";
    elements.navTaskCount.hidden = active === 0;
    elements.navTaskCount.textContent = String(active);
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
        progressCell.innerHTML = `<div class="progress-track"><div class="progress-bar" style="width:${progress.percent}%"></div></div><span class="progress-meta">${escapeHtml(progress.detail)}</span>`;

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
    if (elements.selectAllFiles) {
        elements.selectAllFiles.checked = visible.length > 0 && selectedVisible === visible.length;
        elements.selectAllFiles.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
    }
    if (elements.archiveButton) elements.archiveButton.disabled = selectedFiles.size === 0;
    if (elements.deleteSelectedButton) elements.deleteSelectedButton.disabled = selectedFiles.size === 0;
    if (elements.archiveButton?.lastChild) elements.archiveButton.lastChild.textContent = selectedFiles.size ? `打包下载 (${selectedFiles.size})` : "打包下载";
    const mediaCount = libraryItems.filter((item) => selectedFiles.has(item.path) && ENHANCEABLE_SUFFIXES.has(item.suffix)).length;
    const hasActiveEnhancement = enhancementTasks.some((task) => ["pending", "processing"].includes(task.state));
    if (elements.enhanceButton) elements.enhanceButton.disabled = mediaCount === 0 || hasActiveEnhancement;
    if (elements.enhanceButton?.lastChild) elements.enhanceButton.lastChild.textContent = mediaCount ? `清晰增强 2x (${mediaCount})` : "清晰增强 2x";
    const videoCount = libraryItems.filter((item) => selectedFiles.has(item.path) && ["mp4", "mov", "m4v"].includes(item.suffix)).length;
    const remixBusy = remixTasks.some((task) => ["pending", "processing"].includes(task.state));
    if (elements.remixButton) elements.remixButton.disabled = videoCount === 0 || remixBusy;
    if (elements.remixButton?.lastChild) elements.remixButton.lastChild.textContent = videoCount ? `视频混剪 (${videoCount})` : "视频混剪";
    const imageCount = libraryItems.filter((item) => selectedFiles.has(item.path) && item.ai_compatible).length;
    if (elements.slideshowButton) elements.slideshowButton.disabled = imageCount === 0;
    if (elements.slideshowButton?.lastChild) elements.slideshowButton.lastChild.textContent = imageCount ? `图片成片 (${imageCount})` : "图片成片";
    const liveMedia = selectedLiveMedia();
    const hasActiveLivePhoto = livePhotoTasks.some((task) => ["pending", "processing"].includes(task.state));
    if (elements.livePhotoButton) {
        elements.livePhotoButton.hidden = false;
        elements.livePhotoButton.disabled = selectedFiles.size !== 1 || liveMedia.length !== 1 || hasActiveLivePhoto;
    }
    const aiImages = selectedAIImages();
    const usedCount = Math.min(aiImages.length, 4);
    if (elements.aiVisualCount) {
        if (elements.aiVisualCount.lastChild) elements.aiVisualCount.lastChild.textContent = aiImages.length > 4
            ? `视觉参考 ${usedCount}/${aiImages.length} 张`
            : `视觉参考 ${usedCount} 张`;
        elements.aiVisualCount.title = aiImages.length > 4 ? "每次生成使用列表中靠前的 4 张图片" : "";
    }
}

function selectedAIImages() {
    return libraryItems.filter((item) => selectedFiles.has(item.path) && item.ai_compatible);
}

function selectedLiveMedia() {
    return libraryItems.filter((item) => selectedFiles.has(item.path) && item.live_convertible !== false && LIVE_PHOTO_SUFFIXES.has(item.suffix));
}

function syncAIEditControls() {
    const selectedCount = aiEditSelectedFiles.size;
    const busy = aiImageEditing || aiEditUploading;
    elements.aiEditSelectionCount.textContent = `${selectedCount} / 12`;
    elements.aiEditImagePicker.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
    elements.clearAIEditSelection.disabled = busy || selectedCount === 0;
    elements.aiEditUploadButton.disabled = busy || selectedCount >= 12;
    elements.aiEditImagePicker.setAttribute("aria-busy", String(aiEditUploading));
    elements.editAIImageButton.disabled = busy
        || !aiImageConfigured
        || selectedCount === 0
        || !elements.aiEditPrompt.value.trim();
    elements.batchEditAIImageButton.disabled = busy
        || !aiImageConfigured
        || selectedCount < 2
        || !elements.aiEditPrompt.value.trim();
    elements.nineGridButton.disabled = busy || selectedCount !== 9;
}

async function uploadAIEditImages(fileList) {
    const files = [...(fileList || [])];
    if (!files.length || aiEditUploading || aiImageEditing) return;
    const remaining = 12 - aiEditSelectedFiles.size;
    if (remaining <= 0) {
        showToast("一次最多选择 12 张参考图片", true);
        return;
    }
    const pending = files.slice(0, remaining);
    if (files.length > remaining) showToast(`还可上传 ${remaining} 张，已忽略多余图片`, true);

    aiEditUploading = true;
    syncAIEditControls();
    const uploadedPaths = [];
    const errors = [];
    try {
        for (let index = 0; index < pending.length; index += 1) {
            const file = pending[index];
            elements.aiEditUploadLabel.textContent = `上传中 ${index + 1}/${pending.length}`;
            elements.aiEditUploadHint.textContent = file.name;
            try {
                const result = await api(`/api/ai/images/upload?filename=${encodeURIComponent(file.name)}`, {
                    method: "POST",
                    headers: { "Content-Type": file.type || "application/octet-stream" },
                    body: file,
                });
                uploadedPaths.push(result.image.path);
            } catch (error) {
                errors.push(`${file.name}：${error.message}`);
            }
        }
        uploadedPaths.forEach((path) => aiEditSelectedFiles.add(path));
        if (uploadedPaths.length) {
            libraryFingerprint = "";
            await refreshLibrary();
            renderAIEditPicker();
        }
        if (errors.length) showToast(`已上传 ${uploadedPaths.length} 张，${errors.length} 张失败：${errors[0]}`, true);
        else showToast(`已上传并选中 ${uploadedPaths.length} 张本地图片`);
    } finally {
        aiEditUploading = false;
        elements.aiEditUploadInput.value = "";
        elements.aiEditUploadLabel.textContent = "上传本地图片";
        elements.aiEditUploadHint.textContent = "支持 JPG、PNG、WebP，可多选或拖到下方区域";
        elements.aiEditImagePicker.classList.remove("drag-over");
        syncAIEditControls();
    }
}

function renderAIEditPicker() {
    if (currentRoute().page !== "ai" || currentRoute().aiView !== "image") { syncAIEditControls(); return; }
    const images = libraryItems.filter((item) => item.ai_compatible);
    elements.aiEditImagePicker.replaceChildren();
    if (!images.length) {
        const empty = document.createElement("div");
        empty.className = "picker-empty";
        empty.innerHTML = '<i data-lucide="image-up"></i><span>?????????????????????</span>';
        elements.aiEditImagePicker.append(empty);
        syncAIEditControls();
        refreshIcons();
        return;
    }
    const groups = new Map();
    images.forEach((item) => {
        const parts = item.path.split("/");
        const group = parts.length > 1 ? parts.slice(0, -1).join(" / ") : "????";
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(item);
    });
    groups.forEach((groupItems, groupName) => {
        const heading = document.createElement("div");
        heading.className = "picker-group-title";
        heading.textContent = `${groupName} ? ${groupItems.length} ?`;
        elements.aiEditImagePicker.append(heading);
        groupItems.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `picker-item${aiEditSelectedFiles.has(item.path) ? " selected" : ""}`;
            button.title = item.name;
            button.setAttribute("aria-label", `${aiEditSelectedFiles.has(item.path) ? "????" : "??"} ${item.name}`);
            button.setAttribute("aria-pressed", String(aiEditSelectedFiles.has(item.path)));
            button.disabled = aiEditUploading;
            const image = document.createElement("img");
            image.src = item.thumbnail_url || item.preview_url;
            image.decoding = "async";
            image.alt = "";
            image.loading = "lazy";
            const name = document.createElement("span");
            name.textContent = item.name;
            const check = document.createElement("i");
            check.setAttribute("data-lucide", "check");
            const remove = document.createElement("span");
            remove.className = "picker-remove";
            remove.textContent = "×";
            remove.title = "取消选择";
            remove.setAttribute("role", "button");
            remove.setAttribute("tabindex", "0");
            const removeSelection = (event) => {
                event.preventDefault();
                event.stopPropagation();
                aiEditSelectedFiles.delete(item.path);
                renderAIEditPicker();
            };
            remove.addEventListener("click", removeSelection);
            remove.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") removeSelection(event);
            });
            const deleteImage = document.createElement("span");
            deleteImage.className = "picker-delete";
            deleteImage.title = "删除本地图片";
            deleteImage.setAttribute("role", "button");
            deleteImage.setAttribute("tabindex", "0");
            deleteImage.setAttribute("aria-label", `删除 ${item.name}`);
            deleteImage.innerHTML = '<i data-lucide="trash-2"></i>';
            const deleteLocalImage = async (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (aiEditUploading || aiImageEditing || !confirm(`确定删除 ${item.name}？`)) return;
                try {
                    await api(`/api/library?path=${encodeURIComponent(item.path)}`, { method: "DELETE" });
                    aiEditSelectedFiles.delete(item.path);
                    selectedFiles.delete(item.path);
                    libraryFingerprint = "";
                    await refreshLibrary();
                    showToast("图片已从本地素材库删除");
                } catch (error) { showToast(error.message, true); }
            };
            deleteImage.addEventListener("click", deleteLocalImage);
            deleteImage.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") deleteLocalImage(event);
            });
            button.append(image, name, check, remove, deleteImage);
            button.addEventListener("click", () => {
                if (aiEditSelectedFiles.has(item.path)) aiEditSelectedFiles.delete(item.path);
                else if (aiEditSelectedFiles.size >= 12) {
                    showToast("?????? 12 ?????", true);
                    return;
                } else aiEditSelectedFiles.add(item.path);
                renderAIEditPicker();
            });
            elements.aiEditImagePicker.append(button);
        });
    });
    syncAIEditControls();
    refreshIcons();
}

function openAIImageEditor(item) {
    aiEditSelectedFiles = new Set([item.path]);
    renderAIEditPicker();
    navigateTo("ai", "image");
    window.setTimeout(() => elements.aiEditPrompt.focus(), 0);
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
    const media = viewerItems;
    if (!media.length) return;
    currentMediaIndex = Math.max(0, Math.min(index, media.length - 1));
    const item = media[currentMediaIndex];
    resetMediaViewer();
    elements.mediaViewerTitle.textContent = item.name;
    elements.mediaViewerMeta.textContent = `${item.media_kind === "video" ? (item.is_live ? "Live Photo 动态组件" : "视频") : "图片"} · ${formatBytes(item.size)}`;
    elements.mediaViewerDownload.href = item.download_url;
    elements.mediaViewerDownload.download = item.name;
    elements.copyViewerImage.hidden = !item.copy_url;
    elements.optimizeViewerImage.hidden = !item.import_url;
    elements.productViewerPosition.textContent = item.copy_url ? `${currentMediaIndex + 1} / ${media.length} 张 · 本地原图` : "";
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
    viewerItems = previewableMedia();
    const index = viewerItems.findIndex((entry) => entry.path === item.path);
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
        image.src = item.thumbnail_url || item.preview_url;
        image.decoding = "async";
        image.alt = "";
        image.loading = "lazy";
        button.append(image);
    } else {
        const video = document.createElement("video");
        video.src = item.preview_url;
        video.preload = "none";
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
        live.textContent = "Live Photo";
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
    elements.livePhotoTitle.textContent = task.motion_mode === "ai_object"
        ? "AI 物品运动 · LTX"
        : task.source_kind === "image" ? "图片生成实况 MOV" : "视频裁剪实况 MOV";
    if (task.state === "success") {
        const model = task.motion_model ? ` · ${task.motion_model}` : "";
        elements.livePhotoDetail.textContent = `已生成实况视频：${task.output.split("/").pop()}${model}`;
    }
    else if (task.state === "failed") elements.livePhotoDetail.textContent = task.error || "生成失败";
    else if (task.state === "processing") elements.livePhotoDetail.textContent = task.motion_mode === "ai_object" ? `LTX 正在生成 ${sourceName}` : `正在处理 ${sourceName}`;
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
    const isEmpty = visible.length === 0;
    table.hidden = isEmpty;
    if (elements.fileEmpty) {
        elements.fileEmpty.hidden = !isEmpty;
        const label = elements.fileEmpty.querySelector("span");
        if (label) label.textContent = libraryItems.length && elements.fileSearch?.value.trim()
            ? "没有匹配的文件"
            : "暂无已下载文件";
    }
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
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "icon-button subtle danger-icon file-delete";
        remove.title = "删除文件";
        remove.setAttribute("aria-label", "删除文件");
        remove.innerHTML = '<i data-lucide="trash-2"></i>';
        remove.addEventListener("click", async () => {
            if (!confirm(`确定删除 ${item.name}？`)) return;
            try { await api(`/api/library?path=${encodeURIComponent(item.path)}`, { method: "DELETE" }); selectedFiles.delete(item.path); await refreshLibrary(); showToast("文件已删除"); }
            catch (error) { showToast(error.message, true); }
        });
        action.append(remove);
        if (item.ai_compatible) {
            const edit = createIconButton("wand-sparkles", "用 AI 修改图片", () => openAIImageEditor(item));
            edit.classList.add("file-edit");
            action.append(edit);
        }
        const link = document.createElement("a");
        link.className = "icon-button subtle file-download";
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
    renderAIEditPicker();
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
        const result = await api("/api/library?limit=1000");
        const fingerprint = JSON.stringify(result);
        if (fingerprint === libraryFingerprint) return;
        libraryFingerprint = fingerprint;
        libraryItems = result.items;
        currentState = { ...(currentState || {}), libraryTotal: result.total };
        selectedFiles = new Set([...selectedFiles].filter((path) => libraryItems.some((item) => item.path === path)));
        aiEditSelectedFiles = new Set([...aiEditSelectedFiles].filter((path) => libraryItems.some((item) => item.path === path && item.ai_compatible)));
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

async function refreshRemixTasks() {
    try {
        const result = await api("/api/video/remix");
        remixTasks = result.tasks;
        window.videoRemix?.renderTasks(remixTasks);
        const fingerprint = remixTasks.map((task) => `${task.task_id}:${task.state}`).join("|");
        if (fingerprint !== previousRemixFingerprint && /success|failed/.test(fingerprint)) {
            await refreshLibrary();
            const latest = remixTasks[0];
            if (latest?.state === "success") showToast(`视频混剪完成：${latest.output}`);
            else if (latest?.state === "failed") showToast(latest.error || "视频混剪失败", true);
        }
        previousRemixFingerprint = fingerprint;
        updateSelection();
    } catch (_) { /* best effort while the page is open */ }
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
        if (/(?:https?:\/\/)?(?:[a-z0-9-]+\.)*1688\.com(?:\/|\b)/i.test(content)) {
            elements.alibabaUrls.value = content;
            window.location.hash = "products/1688";
            await startAlibabaCollection([content]);
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
            method: "POST", credentials: "same-origin",
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
    const isAIObject = !isVideo && elements.liveMotionMode.value === "ai_object";
    elements.liveMotionModeField.hidden = isVideo;
    elements.liveMotionPromptField.hidden = !isAIObject;
    elements.liveDurationRange.min = isAIObject ? "2" : "0.5";
    let start = Number(elements.liveStartRange.value) || 0;
    const sourceDuration = elements.livePhotoVideo.duration;
    if (isVideo && Number.isFinite(sourceDuration)) {
        const maxStart = Math.max(0, sourceDuration - 0.5);
        elements.liveStartRange.max = maxStart.toFixed(1);
        start = Math.min(start, maxStart);
        elements.liveStartRange.value = start.toFixed(1);
        const maxDuration = Math.max(0.5, Math.min(5, sourceDuration - start));
        elements.liveDurationRange.max = maxDuration.toFixed(1);
        if (Number(elements.liveDurationRange.value) > maxDuration) elements.liveDurationRange.value = maxDuration.toFixed(1);
    } else {
        elements.liveStartRange.max = "0";
        elements.liveDurationRange.max = "5";
        if (isAIObject && Number(elements.liveDurationRange.value) < 2) elements.liveDurationRange.value = "2";
    }
    elements.liveStartValue.textContent = `${start.toFixed(1)} 秒`;
    elements.liveDurationValue.textContent = `${Number(elements.liveDurationRange.value).toFixed(1)} 秒`;
    elements.createLivePhotoButton.textContent = isAIObject ? "生成 AI 实况" : "开始生成 MOV";
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

function openLivePhotoEditor(requestedSource = null) {
    const source = requestedSource || selectedLiveMedia()[0];
    if (!source || (!requestedSource && selectedFiles.size !== 1)) return;
    resetLivePhotoEditor();
    livePhotoSource = source;
    const sizeDetail = Number.isFinite(Number(source.size)) && Number(source.size) > 0 ? ` · ${formatBytes(source.size)}` : "";
    elements.livePhotoMeta.textContent = `${source.media_kind === "image" ? "图片" : "视频"} · ${source.name}${sizeDetail}`;
    elements.liveStartRange.value = "0";
    elements.liveDurationRange.value = "2";
    elements.liveMotionMode.value = "camera";
    elements.liveMotionPrompt.value = "";
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
    const source = livePhotoSource;
    const sourceKind = source.media_kind;
    const motionMode = sourceKind === "image" ? elements.liveMotionMode.value : "camera";
    elements.createLivePhotoButton.disabled = true;
    try {
        const result = await api("/api/live-photos", { method: "POST", body: JSON.stringify({
            path: source.path,
            start: sourceKind === "video" ? Number(elements.liveStartRange.value) : 0,
            duration: Number(elements.liveDurationRange.value),
            motion_mode: motionMode,
            motion_prompt: sourceKind === "image" ? elements.liveMotionPrompt.value.trim() : "",
        }) });
        elements.livePhotoDialog.close();
        selectedFiles.clear();
        renderLibrary();
        livePhotoTasks = [result.task, ...livePhotoTasks];
        renderLivePhotos();
        window.dispatchEvent(new CustomEvent("live-photo-task-submitted", { detail: { task: result.task, source } }));
        showToast(sourceKind === "video"
            ? "视频裁剪 MOV 任务已提交"
            : motionMode === "ai_object" ? "AI 物品运动任务已提交" : "图片转实况 MOV 任务已提交");
        await refreshLivePhotos();
    } catch (error) { showToast(error.message, true); }
    finally { elements.createLivePhotoButton.disabled = false; }
}

async function createVideoRemix() {
    const items = libraryItems.filter((item) => selectedFiles.has(item.path) && ["mp4", "mov", "m4v"].includes(item.suffix));
    if (items.length) await window.videoRemix.open(items);
}

async function findVideoDuplicates() {
    try {
        const result = await api("/api/video/dedupe", { method: "POST", body: JSON.stringify({ paths: [] }) });
        const count = result.groups.reduce((total, group) => total + group.duplicate_count, 0);
        if (!result.groups.length) showToast("未发现内容完全相同的视频");
        else showToast(`发现 ${result.groups.length} 组重复视频，共 ${count} 个重复文件`);
    } catch (error) { showToast(error.message, true); }
}

async function openSlideshowDialog() {
    const images = libraryItems.filter((item) => selectedFiles.has(item.path) && item.ai_compatible).map((item) => item.path);
    if (!images.length) return;
    const musicSelect = elements.slideshowMusic;
    try {
        const result = await api("/api/video/music");
        musicSelect.replaceChildren(new Option("无音乐", ""));
        result.items.forEach((item) => musicSelect.append(new Option(item.name, item.path)));
    } catch (error) { showToast(error.message, true); return; }
    elements.createSlideshowButton.onclick = async () => {
        elements.createSlideshowButton.disabled = true;
        try {
            const result = await api("/api/video/slideshow", { method: "POST", body: JSON.stringify({ paths: images, seconds: Number(elements.slideshowSeconds.value || 2.5), music: musicSelect.value }) });
            elements.slideshowDialog.close();
            showToast(`已提交图片成片（${images.length} 张）`);
            selectedFiles.clear();
            await refreshLibrary();
        } catch (error) { showToast(error.message, true); }
        finally { elements.createSlideshowButton.disabled = false; }
    };
    elements.slideshowDialog.showModal();
}

function renderAIConfig(config) {
    elements.aiBaseUrl.value = config.base_url || "";
    elements.aiModel.value = config.model || "";
    elements.aiImageBaseUrl.value = config.image_base_url || "http://127.0.0.1:8088/v1";
    elements.aiImageModel.value = config.image_model || "gpt-image-2";
    elements.aiProtocols.forEach((input) => { input.checked = input.value === config.protocol; });
    elements.aiApiKey.value = "";
    elements.clearAIKey.checked = false;
    elements.clearAIKey.disabled = !config.api_key_configured;
    aiImageConfigured = Boolean(config.image_configured);
    aiImageModelName = config.image_model || "";
    if (aiImageConfigured) {
        elements.aiImageEditState.textContent = `${aiImageModelName} · 本地图片中转`;
    } else {
        elements.aiImageEditState.textContent = currentUser?.role === "admin"
            ? "尚未配置图片模型，请在右上角 AI 设置中配置"
            : "图片模型尚未配置，请联系管理员";
    }
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
    syncAIEditControls();
}

function syncAIGenerationMode() {
    const createMode = [...elements.aiGenerationModes].some((input) => input.checked && input.value === "create");
    elements.aiImageOptions.hidden = !createMode;
    elements.generateAIButtonLabel.textContent = createMode ? "生成文案和配图" : "生成文案";
}

const copywritingModeUI = {
    "1": { source: "自己的历史爆款正文", target: false, selling: true, pain: false, keywords: true, purpose: false, title: false, cover: false, own: true },
    "2": { source: "同产品或同赛道对标笔记", target: true, selling: true, pain: false, keywords: true, purpose: false, title: false, cover: false, own: false },
    "3": { source: "其他品类对标笔记", target: true, selling: true, pain: true, keywords: false, purpose: false, title: false, cover: false, own: false },
    "4": { source: "同行爆款或参考正文", target: true, selling: true, pain: true, keywords: false, purpose: false, title: true, cover: true, own: false },
    "5": { source: "需要改写的完整原文", target: true, selling: true, pain: false, keywords: true, purpose: true, title: false, cover: false, own: false },
};

function toggleCopywritingField(field, control, visible, required = false) {
    field.hidden = !visible;
    control.required = visible && required;
}

function syncCopywritingMode() {
    const mode = elements.aiCopywritingMode.value;
    const config = copywritingModeUI[mode];
    elements.aiSourceLabel.textContent = config.source;
    toggleCopywritingField(elements.copyProductField, elements.aiProductName, true, true);
    toggleCopywritingField(elements.copyTargetField, elements.aiTargetAudience, config.target, config.target);
    toggleCopywritingField(elements.copySellingField, elements.aiSellingPoints, config.selling, new Set(["2", "3", "4"]).has(mode));
    toggleCopywritingField(elements.copyPainField, elements.aiPainPoints, config.pain, config.pain);
    toggleCopywritingField(elements.copyKeywordsField, elements.aiKeywords, config.keywords, mode === "1");
    toggleCopywritingField(elements.copyPurposeField, elements.aiProductPurpose, config.purpose, config.purpose);
    toggleCopywritingField(elements.copyTitleField, elements.aiLockedTitle, config.title);
    toggleCopywritingField(elements.copyCoverField, elements.aiCoverDescription, config.cover);
    toggleCopywritingField(elements.copyProhibitedField, elements.aiProhibitedClaims, true);
    toggleCopywritingField(elements.copyOwnPostField, elements.aiOwnPostConfirmed, config.own, config.own);
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

function clearGenerationFeedback() {
    currentGenerationRunId = "";
    elements.generationFeedback.reset();
    elements.generationFeedback.hidden = true;
    elements.knowledgeUsage.textContent = "";
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

function validateCopywritingFields() {
    const fields = [
        [elements.aiProductName, "产品或主题"],
        [elements.aiTargetAudience, "目标人群"],
        [elements.aiSellingPoints, "真实卖点与产品资料"],
        [elements.aiPainPoints, "用户痛点或场景"],
        [elements.aiKeywords, "搜索关键词"],
        [elements.aiProductPurpose, "产品用途或作用"],
        [elements.aiOwnPostConfirmed, "自有爆款来源确认"],
    ];
    const missing = fields.find(([control]) => control.required && (
        control.type === "checkbox" ? !control.checked : !control.value.trim()
    ));
    if (!missing) return true;
    const [control, label] = missing;
    showToast(`请填写${label}`, true);
    control.focus();
    return false;
}

function clearAIEditResult() {
    elements.aiEditResult.hidden = true;
    elements.aiEditEmpty.hidden = false;
    elements.aiEditPreview.removeAttribute("src");
    elements.aiEditPreviewButton.dataset.path = "";
    elements.aiEditDownload.href = "#";
    elements.aiEditDownload.removeAttribute("download");
    elements.aiEditResultMeta.textContent = "";
}

async function generateAIImageEdit() {
    const prompt = elements.aiEditPrompt.value.trim();
    if (!aiEditSelectedFiles.size) {
        showToast("请先选择要修改的图片", true);
        return;
    }
    if (!prompt) {
        showToast("请填写图片修改目标", true);
        elements.aiEditPrompt.focus();
        return;
    }
    aiImageEditing = true;
    syncAIEditControls();
    clearAIEditResult();
    elements.aiImageEditState.textContent = "正在修改图片，请稍候";
    const stopProgressTimer = startAIProgressTimer(elements.aiImageEditState, "本地 Codex 中转正在修改图片");
    try {
        const result = await api("/api/ai/images/edit", {
            method: "POST",
            body: JSON.stringify({
                image_paths: [...aiEditSelectedFiles],
                prompt,
                instructions: elements.aiEditInstructions.value.trim(),
                image_size: elements.aiEditSize.value,
                image_quality: elements.aiEditQuality.value,
            }),
        });
        const item = result.generated_image;
        const [width, height] = elements.aiEditSize.value.split("x").map(Number);
        elements.aiEditPreviewButton.style.aspectRatio = `${width} / ${height}`;
        elements.aiEditPreviewButton.dataset.path = item.path;
        elements.aiEditPreview.src = item.preview_url;
        elements.aiEditDownload.href = item.download_url;
        elements.aiEditDownload.download = item.name;
        const knowledge = result.knowledge_used?.length ? ` · 知识库 ${result.knowledge_used.length} 条` : "";
        elements.aiEditResultMeta.textContent = `${result.image_model} · ${formatBytes(item.size)}${knowledge}`;
        elements.aiEditEmpty.hidden = true;
        elements.aiEditResult.hidden = false;
        elements.aiImageEditState.textContent = `修改完成 · ${result.references_used} 张参考图`;
        historyLoaded = false;
        await loadBilling();
        await refreshLibrary();
        showToast("图片修改完成，已保存到下载目录");
    } catch (error) {
        elements.aiImageEditState.textContent = "图片修改失败";
        showToast(error.message, true);
    } finally {
        stopProgressTimer();
        aiImageEditing = false;
        syncAIEditControls();
    }
}

async function generateBatchAIImageEdit() {
    const prompt = elements.aiEditPrompt.value.trim();
    if (aiEditSelectedFiles.size < 2 || !prompt) return;
    aiImageEditing = true;
    syncAIEditControls();
    elements.aiImageEditState.textContent = `正在逐一优化 ${aiEditSelectedFiles.size} 张图片`;
    try {
        const result = await api("/api/ai/images/edit/batch", {
            method: "POST",
            body: JSON.stringify({ image_paths: [...aiEditSelectedFiles], prompt, instructions: elements.aiEditInstructions.value.trim(), image_size: elements.aiEditSize.value, image_quality: elements.aiEditQuality.value }),
        });
        elements.aiImageEditState.textContent = `批量完成：${result.generated_images.length} 张`;
        elements.aiEditResultMeta.textContent = `${result.image_model} · ${result.generated_images.length} 张结果`;
        showToast(`已完成 ${result.generated_images.length} 张图片优化${result.errors?.length ? `，${result.errors.length} 张失败` : ""}`);
        historyLoaded = false;
        await loadBilling();
        await refreshLibrary();
    } catch (error) {
        elements.aiImageEditState.textContent = "批量修改失败";
        showToast(error.message, true);
    } finally {
        aiImageEditing = false;
        syncAIEditControls();
    }
}

async function generateAIContent() {
    const sourceText = elements.aiSourceText.value.trim();
    const imagePaths = selectedAIImages().slice(0, 4).map((item) => item.path);
    if (!sourceText && !imagePaths.length) {
        showToast("请输入内容或选择参考图片", true);
        elements.aiSourceText.focus();
        return;
    }
    if (!validateCopywritingFields()) return;
    const mode = [...elements.aiGenerationModes].find((input) => input.checked)?.value || "rewrite";
    const generateImage = mode === "create";
    elements.generateAIButton.disabled = true;
    elements.copyAIOutputButton.disabled = true;
    clearGeneratedImage();
    clearGenerationFeedback();
    elements.aiGenerationState.textContent = generateImage ? "正在生成文案和图片" : "正在生成内容";
    elements.aiOutput.placeholder = generateImage ? "AI 正在生成文案和图片..." : "AI 正在分析素材并生成内容...";
    const stopProgressTimer = startAIProgressTimer(
        elements.aiGenerationState,
        generateImage ? "本地 Codex 中转正在生成图片" : "AI 正在生成文案",
    );
    try {
        const result = await api("/api/ai/generate", {
            method: "POST",
            body: JSON.stringify({
                mode,
                copywriting_mode: elements.aiCopywritingMode.value,
                source_text: sourceText,
                instructions: elements.aiInstructions.value.trim(),
                product_name: elements.aiProductName.value.trim(),
                target_audience: elements.aiTargetAudience.value.trim(),
                selling_points: elements.aiSellingPoints.value.trim(),
                pain_points: elements.aiPainPoints.value.trim(),
                keywords: elements.aiKeywords.value.split(/[,，]/).map((value) => value.trim()).filter(Boolean),
                product_purpose: elements.aiProductPurpose.value.trim(),
                locked_title: elements.aiLockedTitle.value.trim(),
                cover_description: elements.aiCoverDescription.value.trim(),
                prohibited_claims: elements.aiProhibitedClaims.value.trim(),
                own_post_confirmed: elements.aiOwnPostConfirmed.checked,
                corpus_ids: selectedCorpus ? [selectedCorpus.id] : [],
                image_paths: imagePaths,
                generate_image: generateImage,
                image_size: elements.aiImageSize.value,
                image_quality: elements.aiImageQuality.value,
            }),
        });
        await loadBilling();
        elements.aiOutput.value = result.text;
        elements.copyAIOutputButton.disabled = !result.text;
        const strategyDetail = result.copywriting_mode_label ? ` · ${result.copywriting_mode_label}` : "";
        const imageDetail = result.images_used ? ` · ${result.images_used} 张参考图` : "";
        const knowledgeDetail = result.knowledge_used?.length ? ` · 知识库 ${result.knowledge_used.length} 条` : "";
        currentGenerationRunId = result.run_id || "";
        historyLoaded = false;
        corpusLoaded = false;
        elements.knowledgeUsage.textContent = result.knowledge_used?.length ? `已参考 ${result.knowledge_used.length} 条知识` : "未匹配知识";
        if (result.ima_status && result.ima_status !== "未启用 IMA") {
            elements.knowledgeUsage.textContent += ` · ${result.ima_status}`;
            elements.knowledgeUsage.title = [...(result.ima_sources || []).map((item) => `${item.library} / ${item.title}（${item.kind}）`), ...(result.ima_warnings || [])].join("\n");
        } else { elements.knowledgeUsage.title = ""; }
        elements.generationFeedback.hidden = !currentGenerationRunId;
        const generatedImage = result.generated_images?.[0];
        if (generatedImage) {
            renderGeneratedImage(generatedImage, result.image_model, elements.aiImageSize.value);
            await refreshLibrary();
            elements.aiGenerationState.textContent = `图文生成完成 · ${result.model}${strategyDetail}${imageDetail}${knowledgeDetail}`;
            showToast("AI 文案和图片已生成");
        } else if (result.image_error) {
            elements.aiGenerationState.textContent = `文案已生成 · 图片生成失败`;
            showToast(result.image_error, true);
        } else {
            elements.aiGenerationState.textContent = `生成完成 · ${result.model}${strategyDetail}${imageDetail}${knowledgeDetail}`;
            showToast("AI 内容已生成");
        }
    } catch (error) {
        elements.aiGenerationState.textContent = "生成失败";
        showToast(error.message, true);
    } finally {
        stopProgressTimer();
        elements.aiOutput.placeholder = "AI 生成结果将在这里显示";
        elements.generateAIButton.disabled = false;
    }
}

async function generateNineGrid() {
    const paths = [...aiEditSelectedFiles];
    if (paths.length !== 9) {
        showToast("\u8bf7\u6b63\u597d\u9009\u62e9 9 \u5f20\u56fe\u7247", true);
        return;
    }
    aiImageEditing = true;
    syncAIEditControls();
    elements.aiImageEditState.textContent = "\u6b63\u5728\u5408\u6210\u4e5d\u5bab\u683c";
    try {
        const result = await api("/api/images/nine-grid", {
            method: "POST",
            body: JSON.stringify({ image_paths: paths }),
        });
        const item = result.generated_image;
        elements.aiEditPreviewButton.style.aspectRatio = "1 / 1";
        elements.aiEditPreviewButton.dataset.path = item.path;
        elements.aiEditPreview.src = item.preview_url;
        elements.aiEditDownload.href = item.download_url;
        elements.aiEditDownload.download = item.name;
        elements.aiEditResultMeta.textContent = `\u4e5d\u5bab\u683c \xb7 ${result.image_count} \u5f20`;
        elements.aiEditEmpty.hidden = true;
        elements.aiEditResult.hidden = false;
        elements.aiImageEditState.textContent = "\u4e5d\u5bab\u683c\u5df2\u751f\u6210";
        await refreshLibrary();
        showToast("\u4e5d\u5bab\u683c\u5df2\u4fdd\u5b58\u5230\u4e0b\u8f7d\u76ee\u5f55");
    } catch (error) {
        elements.aiImageEditState.textContent = "\u4e5d\u5bab\u683c\u751f\u6210\u5931\u8d25";
        showToast(error.message, true);
    } finally {
        aiImageEditing = false;
        syncAIEditControls();
    }
}

async function generateBatchAIImageEditQueued() {
    const prompt = elements.aiEditPrompt.value.trim();
    const paths = [...aiEditSelectedFiles];
    if (paths.length < 2 || !prompt) return;
    aiImageEditing = true;
    syncAIEditControls();
    elements.aiImageEditState.textContent = `正在提交 ${paths.length} 张图片`;
    try {
        const result = await api("/api/ai/images/edit/batch", {
            method: "POST",
            body: JSON.stringify({ image_paths: paths, prompt, instructions: elements.aiEditInstructions.value.trim(), image_size: elements.aiEditSize.value, image_quality: elements.aiEditQuality.value }),
        });
        const taskId = result.task?.task_id;
        if (!taskId) throw new Error("批量任务创建失败");
        let task = result.task;
        for (let attempt = 0; attempt < 180; attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, 1000));
            const status = await api("/api/ai/images/edit/batch-status");
            task = status.tasks.find((item) => item.task_id === taskId) || task;
            elements.aiImageEditState.textContent = `正在处理 ${task.completed}/${task.total} 张图片`;
            if (["success", "partial", "failed"].includes(task.state)) break;
        }
        if (task.state === "failed") throw new Error(task.errors?.[0]?.error || "批量修改失败");
        const gridDetail = task.nine_grid ? " \xb7 \u4e5d\u5bab\u683c\u5df2\u751f\u6210" : "";
        elements.aiImageEditState.textContent = `\u6279\u91cf\u5b8c\u6210\uff1a${task.outputs.length} \u5f20${gridDetail}`;
        elements.aiEditResultMeta.textContent = `${task.image_model || "\u56fe\u7247\u6a21\u578b"} \xb7 ${task.outputs.length} \u5f20\u7ed3\u679c${gridDetail}`;
        if (task.nine_grid) {
            elements.aiEditPreviewButton.style.aspectRatio = "1 / 1";
            elements.aiEditPreviewButton.dataset.path = task.nine_grid.path;
            elements.aiEditPreview.src = task.nine_grid.preview_url;
            elements.aiEditDownload.href = task.nine_grid.download_url;
            elements.aiEditDownload.download = task.nine_grid.name;
            elements.aiEditEmpty.hidden = true;
            elements.aiEditResult.hidden = false;
        }
        showToast(`\u5df2\u5b8c\u6210 ${task.outputs.length} \u5f20\u56fe\u7247\u4f18\u5316${task.nine_grid ? "\uff0c\u4e5d\u5bab\u683c\u5df2\u81ea\u52a8\u751f\u6210" : ""}${task.errors?.length ? `\uff0c${task.errors.length} \u5f20\u5931\u8d25` : ""}`);
        historyLoaded = false;
        await loadBilling();
        await refreshLibrary();
    } catch (error) {
        elements.aiImageEditState.textContent = "批量修改失败";
        showToast(error.message, true);
    } finally {
        aiImageEditing = false;
        syncAIEditControls();
    }
}

async function submitGenerationFeedback(event) {
    event.preventDefault();
    if (!currentGenerationRunId) return;
    elements.saveGenerationFeedbackButton.disabled = true;
    try {
        const result = await api(`/api/knowledge/runs/${encodeURIComponent(currentGenerationRunId)}/feedback`, {
            method: "POST",
            body: JSON.stringify({
                rating: Number(elements.generationRating.value),
                feedback: elements.generationFeedbackText.value.trim(),
                reusable_lesson: elements.reusableLesson.value.trim(),
            }),
        });
        elements.generationFeedback.hidden = true;
        showToast(result.knowledge_entry ? "反馈已保存，可复用经验已进入知识库" : "生成反馈已保存");
    } catch (error) { showToast(error.message, true); }
    finally { elements.saveGenerationFeedbackButton.disabled = false; }
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

function addRecordFact(container, label, value) {
    if (value === null || value === undefined || value === "") return;
    const item = document.createElement("div");
    const name = document.createElement("span");
    const content = document.createElement("strong");
    name.textContent = label;
    content.textContent = String(value);
    item.append(name, content);
    container.append(item);
}

function historyKindLabel(run) {
    if (run.mode === "image-edit") return "图片修改";
    if (run.generated_image) return "图文生成";
    return "文案生成";
}

function historyStrategyLabel(run) {
    const mode = String(run.request_payload?.copywriting_mode || run.mode.match(/mengge-(\d)/)?.[1] || "");
    return {
        "1": "1:1 贴近仿写",
        "2": "创新性写笔记",
        "3": "跨产品模仿",
        "4": "定题真人种草",
        "5": "场景化素人仿写",
    }[mode] || "通用创作";
}

function renderHistoryList() {
    elements.historyList.replaceChildren();
    elements.historySummary.textContent = historyTotal
        ? `共 ${historyTotal} 条记录，当前显示 ${historyItems.length} 条`
        : "暂无符合条件的创作记录";
    historyItems.forEach((run) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `record-row${selectedHistory?.id === run.id ? " active" : ""}`;
        const heading = document.createElement("div");
        heading.className = "record-row-heading";
        const title = document.createElement("strong");
        title.textContent = run.title;
        const kind = document.createElement("span");
        kind.className = "record-kind";
        kind.textContent = historyKindLabel(run);
        heading.append(title, kind);
        const preview = document.createElement("p");
        preview.textContent = run.output_preview || "未保存文本结果";
        const meta = document.createElement("div");
        meta.className = "record-row-meta";
        const time = document.createElement("span");
        time.textContent = formatTime(run.created_at);
        const rating = document.createElement("span");
        rating.textContent = run.rating ? `${run.rating} 星` : historyStrategyLabel(run);
        meta.append(time, rating);
        button.append(heading, preview, meta);
        button.addEventListener("click", () => selectHistory(run.id).catch((error) => showToast(error.message, true)));
        elements.historyList.append(button);
    });
    elements.historyLoadMore.hidden = historyItems.length >= historyTotal;
    refreshIcons();
}

function renderHistoryDetail(run) {
    elements.historyEmpty.hidden = true;
    elements.historyDetail.hidden = false;
    elements.historyDetailKind.textContent = historyKindLabel(run);
    elements.historyDetailTitle.textContent = run.title;
    elements.historyDetailMeta.textContent = `${formatTime(run.created_at)} · ${run.model || "未记录模型"}`;
    elements.historyFacts.replaceChildren();
    addRecordFact(elements.historyFacts, "创作策略", historyStrategyLabel(run));
    addRecordFact(elements.historyFacts, "知识参考", `${run.knowledge_ids.length} 条`);
    addRecordFact(elements.historyFacts, "爆款素材", `${run.corpus_ids.length} 条`);
    addRecordFact(elements.historyFacts, "生成图片", `${run.generated_images.length} 张`);
    const billing = run.request_payload?.billing || {};
    const billedUnits = Object.values(billing).reduce((total, item) => total + Number(item?.units || 0), 0);
    addRecordFact(elements.historyFacts, "本次消耗", billedUnits ? `${billedUnits} 点` : "旧记录");
    addRecordFact(elements.historyFacts, "存储版本", run.storage || "历史记录");

    elements.historyImages.replaceChildren();
    run.generated_images.forEach((item) => {
        const figure = document.createElement("figure");
        const preview = document.createElement("a");
        preview.href = item.preview_url;
        preview.target = "_blank";
        preview.rel = "noopener";
        preview.title = "打开原图";
        const image = document.createElement("img");
        image.src = item.thumbnail_url || item.preview_url;
        image.decoding = "async";
        image.alt = item.name;
        image.loading = "lazy";
        preview.append(image);
        const download = document.createElement("a");
        download.className = "history-image-download";
        download.href = item.download_url;
        download.download = item.name;
        download.innerHTML = '<i data-lucide="download"></i><span>下载</span>';
        figure.append(preview, download);
        elements.historyImages.append(figure);
    });
    elements.historyImages.hidden = run.generated_images.length === 0;
    elements.historyOutput.textContent = run.output_text || "未保存文本结果";
    const source = [run.source_text, run.instructions ? `补充要求：${run.instructions}` : ""].filter(Boolean).join("\n\n");
    elements.historySource.textContent = source;
    elements.historySourceSection.hidden = !source;
    if (run.rating || run.feedback || run.reusable_lesson) {
        const feedback = [
            run.rating ? `评分：${run.rating} 星` : "",
            run.feedback ? `反馈：${run.feedback}` : "",
            run.reusable_lesson ? `已沉淀经验：${run.reusable_lesson}` : "",
        ].filter(Boolean);
        elements.historyFeedback.textContent = feedback.join("\n");
        elements.historyFeedback.hidden = false;
    } else {
        elements.historyFeedback.hidden = true;
        elements.historyFeedback.textContent = "";
    }
    refreshIcons();
}

async function selectHistory(runId) {
    const run = await api(`/api/ai/history/${encodeURIComponent(runId)}`);
    selectedHistory = run;
    renderHistoryList();
    renderHistoryDetail(run);
}

async function loadHistory(append = false) {
    if (historyLoading) return;
    historyLoading = true;
    elements.refreshHistoryButton.disabled = true;
    elements.historyLoadMore.disabled = true;
    if (!append) elements.historySummary.textContent = "正在读取创作历史";
    try {
        const params = new URLSearchParams({
            query: elements.historySearch.value.trim(),
            limit: "30",
            offset: String(append ? historyItems.length : 0),
        });
        const result = await api(`/api/ai/history?${params}`);
        historyItems = append ? historyItems.concat(result.items) : result.items;
        historyTotal = result.total;
        historyLoaded = true;
        if (!append) selectedHistory = null;
        renderHistoryList();
        if (!historyItems.length) {
            elements.historyDetail.hidden = true;
            elements.historyEmpty.hidden = false;
        } else if (!selectedHistory) {
            await selectHistory(historyItems[0].id);
        }
    } finally {
        historyLoading = false;
        elements.refreshHistoryButton.disabled = false;
        elements.historyLoadMore.disabled = false;
    }
}

function safeExternalUrl(value) {
    if (!value) return "";
    try {
        const url = new URL(value);
        return new Set(["http:", "https:"]).has(url.protocol) ? url.href : "";
    } catch (_) {
        return "";
    }
}

function renderCorpusList() {
    elements.corpusList.replaceChildren();
    elements.corpusSummary.textContent = corpusTotal
        ? `已整理 ${corpusTotal} 条案例，当前显示 ${corpusItems.length} 条`
        : "素材库中暂无符合条件的案例";
    elements.aiCorpusStatus.lastChild.textContent = `爆款素材 ${corpusTotal} 条`;
    corpusItems.forEach((entry) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `record-row${selectedCorpus?.id === entry.id ? " active" : ""}`;
        const heading = document.createElement("div");
        heading.className = "record-row-heading";
        const title = document.createElement("strong");
        title.textContent = entry.product_name;
        const cart = document.createElement("span");
        cart.className = "record-kind corpus-count";
        cart.textContent = entry.add_to_cart_24h === null ? "案例" : `24h ${entry.add_to_cart_24h.toLocaleString("zh-CN")} 加购`;
        heading.append(title, cart);
        const preview = document.createElement("p");
        preview.textContent = entry.content_preview;
        const meta = document.createElement("div");
        meta.className = "record-row-meta";
        const tags = document.createElement("span");
        tags.textContent = entry.tags.slice(0, 3).join(" · ") || `案例 ${entry.record_number}`;
        const uses = document.createElement("span");
        uses.textContent = `参考 ${entry.use_count} 次`;
        meta.append(tags, uses);
        button.append(heading, preview, meta);
        button.addEventListener("click", () => selectCorpus(entry.id).catch((error) => showToast(error.message, true)));
        elements.corpusList.append(button);
    });
    elements.corpusLoadMore.hidden = corpusItems.length >= corpusTotal;
}

function addCorpusLink(label, value) {
    const url = safeExternalUrl(value);
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.innerHTML = `<i data-lucide="external-link"></i><span>${label}</span>`;
    elements.corpusLinks.append(link);
}

function renderCorpusDetail(entry) {
    elements.corpusEmpty.hidden = true;
    elements.corpusDetail.hidden = false;
    elements.corpusDetailTitle.textContent = entry.product_name;
    elements.corpusDetailMeta.textContent = `${entry.source_name} · 第 ${entry.record_number} 条`;
    elements.corpusFacts.replaceChildren();
    addRecordFact(elements.corpusFacts, "24 小时加购", entry.add_to_cart_24h === null ? "未记录" : `${entry.add_to_cart_24h.toLocaleString("zh-CN")} 人`);
    addRecordFact(elements.corpusFacts, "账号粉丝", entry.followers_text || "未记录");
    addRecordFact(elements.corpusFacts, "案例销量", entry.sales_text || "未记录");
    addRecordFact(elements.corpusFacts, "被参考", `${entry.use_count} 次`);

    elements.corpusGallery.replaceChildren();
    entry.image_paths.forEach((path, index) => {
        const link = document.createElement("a");
        link.href = `/api/ai/corpus/${encodeURIComponent(entry.id)}/images/${index}`;
        link.target = "_blank";
        link.rel = "noopener";
        link.title = `查看素材图 ${index + 1}`;
        const image = document.createElement("img");
        image.src = link.href;
        image.alt = `${entry.product_name} 素材图 ${index + 1}`;
        image.loading = "lazy";
        link.append(image);
        elements.corpusGallery.append(link);
    });
    elements.corpusGallery.hidden = entry.image_paths.length === 0;
    elements.corpusContent.textContent = entry.content;
    elements.corpusLinks.replaceChildren();
    addCorpusLink("查看飞书原始记录", entry.source_url);
    addCorpusLink("打开案例链接", entry.product_url);
    refreshIcons();
}

async function selectCorpus(entryId) {
    const entry = await api(`/api/ai/corpus/${encodeURIComponent(entryId)}`);
    selectedCorpus = entry;
    renderCorpusList();
    renderCorpusDetail(entry);
}

async function refreshCorpusStatus() {
    const result = await api("/api/ai/corpus?limit=1");
    corpusTotal = result.total;
    elements.aiCorpusStatus.lastChild.textContent = `爆款素材 ${corpusTotal} 条`;
}

async function loadCorpus(append = false) {
    if (corpusLoading) return;
    corpusLoading = true;
    elements.refreshCorpusButton.disabled = true;
    elements.corpusLoadMore.disabled = true;
    if (!append) elements.corpusSummary.textContent = "正在读取爆款素材";
    try {
        const params = new URLSearchParams({
            query: elements.corpusSearch.value.trim(),
            limit: "30",
            offset: String(append ? corpusItems.length : 0),
        });
        const result = await api(`/api/ai/corpus?${params}`);
        corpusItems = append ? corpusItems.concat(result.items) : result.items;
        corpusTotal = result.total;
        corpusLoaded = true;
        if (!append) selectedCorpus = null;
        renderCorpusList();
        if (!corpusItems.length) {
            elements.corpusDetail.hidden = true;
            elements.corpusEmpty.hidden = false;
        } else if (!selectedCorpus) {
            await selectCorpus(corpusItems[0].id);
        }
    } finally {
        corpusLoading = false;
        elements.refreshCorpusButton.disabled = false;
        elements.corpusLoadMore.disabled = false;
    }
}

function reuseHistory() {
    if (!selectedHistory) return;
    const request = selectedHistory.request_payload || {};
    if (selectedHistory.mode === "image-edit") {
        const available = new Set(libraryItems.filter((item) => item.ai_compatible).map((item) => item.path));
        aiEditSelectedFiles = new Set((request.image_paths || []).filter((path) => available.has(path)).slice(0, 12));
        elements.aiEditPrompt.value = request.prompt || selectedHistory.source_text || "";
        elements.aiEditInstructions.value = request.instructions || "";
        elements.aiEditSize.value = request.image_size || "1024x1536";
        elements.aiEditQuality.value = request.image_quality || "medium";
        clearAIEditResult();
        renderAIEditPicker();
        navigateTo("ai", "image");
        elements.aiEditPrompt.focus();
        if (!aiEditSelectedFiles.size) showToast("原参考图片已不在下载目录，请重新选择", true);
        return;
    }
    const fields = {
        source_text: elements.aiSourceText,
        instructions: elements.aiInstructions,
        product_name: elements.aiProductName,
        target_audience: elements.aiTargetAudience,
        selling_points: elements.aiSellingPoints,
        pain_points: elements.aiPainPoints,
        product_purpose: elements.aiProductPurpose,
        locked_title: elements.aiLockedTitle,
        cover_description: elements.aiCoverDescription,
        prohibited_claims: elements.aiProhibitedClaims,
    };
    Object.entries(fields).forEach(([key, control]) => { control.value = request[key] || ""; });
    elements.aiKeywords.value = Array.isArray(request.keywords) ? request.keywords.join("，") : "";
    elements.aiOwnPostConfirmed.checked = Boolean(request.own_post_confirmed);
    elements.aiCopywritingMode.value = request.copywriting_mode || "2";
    elements.aiGenerationModes.forEach((input) => { input.checked = input.value === (request.mode || "rewrite"); });
    const available = new Set(libraryItems.map((item) => item.path));
    selectedFiles = new Set((request.image_paths || []).filter((path) => available.has(path)));
    elements.aiOutput.value = "";
    elements.copyAIOutputButton.disabled = true;
    clearGeneratedImage();
    clearGenerationFeedback();
    syncAIGenerationMode();
    syncCopywritingMode();
    renderLibrary();
    navigateTo("ai", "copy");
    elements.aiSourceText.focus();
}

function useCorpusForCreation() {
    if (!selectedCorpus) return;
    elements.aiCopywritingMode.value = "2";
    elements.aiGenerationModes.forEach((input) => { input.checked = input.value === "rewrite"; });
    elements.aiSourceText.value = selectedCorpus.content;
    elements.aiProductName.value = selectedCorpus.product_name;
    elements.aiTargetAudience.value = "";
    elements.aiSellingPoints.value = "";
    elements.aiKeywords.value = selectedCorpus.tags.join("，");
    elements.aiInstructions.value = "参考案例的选题、场景、开头钩子和成交结构进行创新重写；不要照抄原文，不要沿用案例中的价格、销量、功效或用户经历。";
    elements.aiOwnPostConfirmed.checked = false;
    elements.aiOutput.value = "";
    elements.copyAIOutputButton.disabled = true;
    clearGeneratedImage();
    clearGenerationFeedback();
    syncAIGenerationMode();
    syncCopywritingMode();
    navigateTo("ai", "copy");
    elements.aiTargetAudience.focus();
    showToast("案例结构已带入，请补充目标人群和当前产品的真实资料");
}

async function copyHistoryOutput() {
    if (!selectedHistory?.output_text) return;
    try {
        await navigator.clipboard.writeText(selectedHistory.output_text);
        showToast("历史内容已复制");
    } catch (_) {
        showToast("复制失败，请在内容区域手动复制", true);
    }
}

async function deleteHistory() {
    if (!selectedHistory || !window.confirm("确定删除这条创作记录吗？此操作不可恢复。")) return;
    const runId = selectedHistory.id;
    elements.deleteHistoryButton.disabled = true;
    try {
        await api(`/api/ai/history/${encodeURIComponent(runId)}`, { method: "DELETE" });
        selectedHistory = null;
        historyLoaded = false;
        await loadHistory();
        showToast("创作记录已删除");
    } finally {
        elements.deleteHistoryButton.disabled = false;
    }
}

function localProductImages(item) {
    return [...new Set([...(Array.isArray(item.images) ? item.images : []), ...(Array.isArray(item.detail_images) ? item.detail_images : []), ...(Array.isArray(item.sku_images) ? item.sku_images : [])].filter((path) => typeof path === "string" && path && !/^(?:https?:|\/\/)/i.test(path)))];
}

function localProductVideos(item) {
    return (Array.isArray(item.videos) ? item.videos : []).filter((path) => typeof path === "string" && path && !/^(?:https?:|\/\/)/i.test(path));
}

function productVideoUrl(source, item, index) {
    return `/api/product-videos/${source}/${encodeURIComponent(item.product_id)}/${index}`;
}

function productImageUrl(source, item, index) {
    return `/api/product-images/${source}/${encodeURIComponent(item.product_id)}/${index}`;
}

function renderProductCards(container, products, source) {
    productRecords[source] = products;
    container.replaceChildren();
    if (!products.length) {
        container.innerHTML = '<div class="product-empty"><i data-lucide="package-open"></i><strong>商品素材库还是空的</strong><p>粘贴商品详情分享链接，开始保存商品信息与图片</p></div>';
        refreshIcons();
        return;
    }
    products.forEach((item, recordIndex) => {
        const images = localProductImages(item);
        const videos = localProductVideos(item);
        const first = productImageUrl(source, item, 0);
        const article = document.createElement("article");
        article.className = "alibaba-card";
        const imageGroup = (paths, label) => !paths.length ? "" : `<div class="product-image-group"><p class="product-group-label">${label} · ${paths.length} 张</p><div class="product-thumbnails">${paths.map((path, offset) => { const index = images.indexOf(path); return `<button type="button" class="product-thumb" data-product-action="preview" data-image-index="${index}" title="查看${label} ${offset + 1}"><img src="${productImageUrl(source, item, index)}?format=thumbnail" alt="${label} ${offset + 1}" loading="lazy" decoding="async"></button>`; }).join("")}</div></div>`;
        const thumbnails = imageGroup(localProductImages({images:item.images}), "商品主图") + imageGroup(localProductImages({images:item.detail_images}), "图文详情") + imageGroup(localProductImages({images:item.sku_images}), "SKU 规格图");
        const specs = Object.entries(item.specs || {});
        const imageErrors = item.image_errors || [];
        const missingDetails = Boolean(item.detail_url) && localProductImages({ images: item.detail_images }).length === 0;
        const missingSkus = source === "1688" && !Array.isArray(item.sku_image_urls);
        const missingVideos = source === "1688" && (!Array.isArray(item.video_urls) || item.video_errors?.length || (item.video_urls.length && !videos.length));
        const videoGroup = videos.length ? `<div class="product-video-group"><p class="product-group-label">主图视频 · ${videos.length} 个</p>${videos.map((_, index) => `<div class="product-video-row"><button class="button secondary" type="button" data-product-action="video" data-video-index="${index}"><i data-lucide="play-circle"></i>播放商品视频 ${index + 1}</button><button class="button secondary" type="button" data-product-action="remix" data-video-index="${index}"><i data-lucide="scissors"></i>直接混剪</button><a class="button secondary" href="${productVideoUrl(source, item, index)}?download=true" download><i data-lucide="download"></i>下载视频</a></div>`).join("")}</div>` : "";
        const sourceLink = /^https?:\/\//i.test(item.url || "") ? `<a class="product-source" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">查看源商品 <i data-lucide="external-link"></i></a>` : "";
        article.innerHTML = `<div class="product-visual">${images.length ? `<button type="button" class="product-cover" data-product-action="preview" data-image-index="0" title="放大查看商品图片"><img src="${first}?format=thumbnail" alt="${escapeHtml(item.title || "商品图片")}" loading="lazy" decoding="async"><span>点击查看原图</span></button>` : '<div class="product-cover product-cover-empty"><i data-lucide="image-off"></i><strong>商品图尚未保存</strong><span>点击下方「补齐素材」重新下载</span></div>'}<span class="product-image-count">${images.length} 张本地图片${videos.length ? ` · ${videos.length} 个视频` : ""}</span></div><div class="product-card-body"><div class="product-source-line"><span class="product-platform">${source === "1688" ? "1688" : "小红书"}</span>${sourceLink}</div><h3>${escapeHtml(item.title || "未命名商品")}</h3><div class="product-price">${escapeHtml(item.price ? `¥ ${item.price}` : "价格未公开")}${item.price_label ? `<span class="product-price-label">${escapeHtml(item.price_label)}</span>` : ""}${item.original_price && item.original_price !== item.price ? `<del class="product-original-price">¥ ${escapeHtml(item.original_price)}</del>` : ""}</div>${item.shop ? `<p>${escapeHtml(item.shop)}${item.sales ? ` · ${escapeHtml(item.sales)}` : ""}</p>` : ""}<div class="product-image-groups">${thumbnails}</div>${videoGroup}<div class="product-card-actions">${source === "1688" ? '<button class="button primary" type="button" data-product-action="listing">小红书上品</button>' : ""}<button class="button secondary" type="button" data-product-action="copy" ${images.length ? "" : "disabled"}><i data-lucide="copy"></i>复制图片</button>${images.length || videos.length ? `<a class="button secondary" href="/api/product-images/${source}/${encodeURIComponent(item.product_id)}/archive" download><i data-lucide="download"></i>打包素材</a>` : ""}<button class="button primary" type="button" data-product-action="optimize" ${images.length ? "" : "disabled"}><i data-lucide="wand-sparkles"></i>AI 优化</button></div>${!images.length || imageErrors.length || missingDetails || missingVideos || missingSkus || item.asset_status?.state === "partial" ? '<button class="button secondary product-repair" type="button" data-product-action="repair"><i data-lucide="refresh-cw"></i>补齐素材</button>' : ""}${imageErrors.length ? `<p class="product-image-error">${imageErrors.length} 张图片下载失败，已保留下载成功的图片</p>` : ""}${item.video_errors?.length ? '<p class="product-image-error">视频下载失败，请点击补齐素材重试</p>' : ""}${specs.length ? `<details class="product-specifications"><summary>查看 ${specs.length} 项商品规格</summary><dl>${specs.map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl></details>` : ""}</div>`;
        article.querySelectorAll("[data-product-action]").forEach((button) => button.addEventListener("click", async () => {
            if (button.dataset.productAction === "listing") return window.commerceWorkspace.create(item.product_id);
            const imageIndex = Number(button.dataset.imageIndex || 0);
            if (button.dataset.productAction === "remix") return window.videoRemix.importProduct(source, item.product_id, Number(button.dataset.videoIndex || 0));
            if (button.dataset.productAction === "video") return openProductVideo(source, recordIndex, Number(button.dataset.videoIndex || 0));
            if (button.dataset.productAction === "preview") return openProductViewer(source, recordIndex, imageIndex);
            if (button.dataset.productAction === "copy") return copyProductImage(first + "?format=png");
            if (button.dataset.productAction === "optimize") return importProductForAI(first + "/import");
            button.disabled = true;
            try {
                const result = await api(`/api/product-images/${source}/${encodeURIComponent(item.product_id)}/repair`, { method: "POST" });
                await (source === "1688" ? loadAlibabaProducts() : loadXhsProducts());
                const count = localProductImages(result.product).length;
                const videoCount = localProductVideos(result.product).length;
                const errors = (result.product.image_errors || []).length + (result.product.video_errors || []).length;
                showToast(`已保存 ${count} 张图片、${videoCount} 个视频${errors ? `，${errors} 项素材下载失败，可再次补齐` : ""}`, Boolean(errors));
            } catch (error) { showToast(error.message, true); }
            finally { button.disabled = false; }
        }));
        container.append(article);
    });
    refreshIcons();
}

function renderAlibabaProducts(products) {
    elements.alibabaSummary.textContent = products.length ? `已保存 ${products.length} 个商品 · ${products.reduce((count, item) => count + localProductImages(item).length, 0)} 张本地图片` : "商品信息和原图一并保存到本地";
    renderProductCards(elements.alibabaProducts, products, "1688");
}

function openProductViewer(source, recordIndex, imageIndex) {
    const item = productRecords[source][recordIndex];
    viewerItems = localProductImages(item).map((path, index) => {
        const url = productImageUrl(source, item, index);
        const mainCount = localProductImages({ images: item.images }).length;
        const imageLabel = index < mainCount ? `主图 ${index + 1}` : `详情图 ${index - mainCount + 1}`;
        return { path, name: `${item.title} · ${imageLabel}`, media_kind: "image", preview_url: url,
            download_url: url + "?download=true", copy_url: url + "?format=png", import_url: url + "/import" };
    });
    showMediaAt(imageIndex);
    if (!elements.mediaViewerDialog.open) elements.mediaViewerDialog.showModal();
}

function openProductVideo(source, recordIndex, videoIndex) {
    const item = productRecords[source][recordIndex];
    viewerItems = localProductVideos(item).map((path, index) => {
        const url = productVideoUrl(source, item, index);
        return { path, name: `${item.title} · 主图视频 ${index + 1}`, media_kind: "video", size: item.video_sizes?.[index],
            preview_url: url, download_url: url + "?download=true" };
    });
    showMediaAt(videoIndex);
    if (!elements.mediaViewerDialog.open) elements.mediaViewerDialog.showModal();
}

async function copyProductImage(url) {
    try {
        const png = fetch(url, { credentials: "same-origin" }).then(async (response) => {
            if (!response.ok) throw new Error("商品图片读取失败");
            return response.blob();
        });
        await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
        showToast("图片已复制，可直接粘贴到编辑器或聊天窗口");
    } catch (_) { showToast("图片复制失败，请允许剪贴板权限，或点击下载原图", true); }
}

async function importProductForAI(importUrl) {
    try {
        const item = await api(importUrl, { method: "POST" });
        await refreshLibrary();
        if (!libraryItems.some((entry) => entry.path === item.path)) libraryItems.unshift(item);
        aiEditSelectedFiles = new Set([item.path]);
        elements.aiEditPrompt.value = "去除图片上的叠加水印和干扰文字，保留商品真实的品牌标识、颜色、材质、形状和细节，优化清晰度和光线。";
        elements.mediaViewerDialog.close();
        navigateTo("ai", "image");
        renderAIEditPicker();
        showToast("原图已放入本地素材库，可调整要求后开始 AI 优化");
    } catch (error) { showToast(error.message, true); }
}

function renderXhsProductJob(job) {
    if (!job) return;
    xhsProductJobId = job.state === "processing" ? job.id : "";
    elements.xhsProductCollect.disabled = Boolean(xhsProductJobId);
    elements.xhsProductSummary.textContent = xhsProductJobId ? `${job.phase || "读取商品信息"} · ${job.completed}/${job.total}` : job.state === "failed" ? "商品采集失败，请查看下方原因" : `本次保存 ${job.collected} 个商品${job.errors?.length ? "，部分图片待补齐" : "和商品图片"}`;
    elements.xhsProductErrors.replaceChildren();
    (job.errors || []).forEach((error) => { const line = document.createElement("p"); line.textContent = error.message; elements.xhsProductErrors.append(line); });
    elements.xhsProductErrors.hidden = !job.errors?.length;
}

async function loadXhsProducts() {
    const result = await api("/api/xhs/products");
    renderProductCards(elements.xhsProducts, result.products || [], "xhs");
    renderXhsProductJob(result.job);
}

async function refreshXhsProductJob() {
    if (!xhsProductJobId) return;
    try {
        const result = await api("/api/xhs/products/status");
        renderXhsProductJob(result.job);
        if (!xhsProductJobId) await loadXhsProducts();
    } catch (error) { elements.xhsProductSummary.textContent = error.message; }
}

async function collectXhsProducts() {
    elements.xhsProductCollect.disabled = true;
    try {
        const result = await api("/api/xhs/products", { method: "POST", body: JSON.stringify({ content: elements.xhsProductUrl.value.trim() }) });
        renderXhsProductJob(result.job);
        if (!xhsProductJobId) await loadXhsProducts();
    } catch (error) { elements.xhsProductSummary.textContent = error.message; showToast(error.message, true); }
    finally { elements.xhsProductCollect.disabled = Boolean(xhsProductJobId); }
}

async function loadAlibabaProducts() {
    const result = await api("/api/1688/products");
    renderAlibabaProducts(result.products || []);
    alibabaJobFingerprint = "";
    renderAlibabaJob(result.job);
}

function renderAlibabaJob(job) {
    if (!job) return;
    alibabaJobId = job.state === "processing" ? job.id : "";
    elements.alibabaCollect.disabled = Boolean(alibabaJobId);
    const fingerprint = JSON.stringify(job);
    if (fingerprint === alibabaJobFingerprint) return;
    alibabaJobFingerprint = fingerprint;
    const errors = job.errors || [];
    if (alibabaJobId) elements.alibabaSummary.textContent = `正在采集 ${job.completed}/${job.total} · ${job.phase || "读取商品信息"}`;
    else if (job.state === "failed") elements.alibabaSummary.textContent = "本次未取得商品信息，已保留之前的采集结果";
    else elements.alibabaSummary.textContent = `本次采集 ${job.collected} 个商品${errors.length ? `，${errors.length} 个链接失败` : ""}`;
    elements.alibabaErrors.replaceChildren();
    errors.forEach((error) => {
        const line = document.createElement("p");
        line.textContent = `${error.title || error.url || "采集失败"}：${error.message}`;
        elements.alibabaErrors.append(line);
    });
    elements.alibabaErrors.hidden = errors.length === 0;
}

async function refreshAlibabaJob() {
    if (!alibabaJobId) return;
    try {
        const result = await api("/api/1688/status");
        renderAlibabaJob(result.job);
        if (!alibabaJobId) await loadAlibabaProducts();
    } catch (error) { elements.alibabaSummary.textContent = `状态读取失败：${error.message}`; }
}

async function startAlibabaCollection(urls, keyword = "") {
    elements.alibabaCollect.disabled = true;
    try {
        const result = await api("/api/1688/collect", { method: "POST", body: JSON.stringify({ urls, keyword, limit: 100 }) });
        alibabaJobFingerprint = "";
        renderAlibabaJob(result.job);
        showToast("1688 采集已提交，可继续使用页面");
        if (!alibabaJobId) await loadAlibabaProducts();
    } finally { elements.alibabaCollect.disabled = Boolean(alibabaJobId); }
}

async function collectAlibabaProducts() {
    const urls = elements.alibabaUrls.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
    try { await startAlibabaCollection(urls, elements.alibabaKeyword.value); }
    catch (error) {
        elements.alibabaSummary.textContent = error.message;
        showToast(error.message, true);
    }
}

async function persistAIConfig(closeDialog = true) {
    const result = await api("/api/ai/config", {
        method: "PUT",
        body: JSON.stringify({
            base_url: elements.aiBaseUrl.value,
            api_key: elements.aiApiKey.value,
            model: elements.aiModel.value,
            image_base_url: elements.aiImageBaseUrl.value,
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
        const imageModelStatus = result.image_model_available === false ? "，图片模型未在本地中转列表中" : "";
        const imageLatency = result.image_relay_latency_ms ?? result.latency_ms;
        const imageEndpoint = result.image_transport === "openai_images" ? "/images/generations" : "/responses";
        elements.aiConfigState.textContent = `连接成功 · 文案 ${result.latency_ms} ms · 图片 ${imageLatency} ms`;
        showToast(`本地 AI 中转连接成功，文案和图片共用 ${imageEndpoint}${modelStatus}${imageModelStatus}`);
    } catch (error) {
        elements.aiConfigState.textContent = "连接失败";
        showToast(error.message, true);
    } finally {
        elements.testAIButton.disabled = false;
        elements.saveAIButton.disabled = false;
    }
}

elements.navItems.forEach((button) => {
    button.addEventListener("click", () => navigateTo(button.dataset.route));
});
elements.aiViewTabs.forEach((button) => {
    button.addEventListener("click", () => navigateTo("ai", button.dataset.aiView));
});
window.addEventListener("hashchange", activateRoute);
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
elements.billingButton.addEventListener("click", async () => {
    elements.billingDialog.showModal();
    try {
        await loadBilling();
    } catch (error) { showToast(error.message, true); }
});
elements.knowledgeButton.addEventListener("click", async () => {
    resetKnowledgeEditor();
    elements.knowledgeDialog.showModal();
    try { await loadKnowledge(); } catch (error) { showToast(error.message, true); }
});
elements.knowledgeForm.addEventListener("submit", saveKnowledge);
elements.resetKnowledgeForm.addEventListener("click", resetKnowledgeEditor);
elements.knowledgeFilter.addEventListener("change", () => loadKnowledge().catch((error) => showToast(error.message, true)));
elements.knowledgeSearch.addEventListener("input", () => {
    clearTimeout(knowledgeSearchTimer);
    knowledgeSearchTimer = setTimeout(() => loadKnowledge().catch((error) => showToast(error.message, true)), 250);
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

// Keep the image editor copy in one place so stale encoded labels cannot leak into the UI.
const AI_IMAGE_COPY = {
    editorTitle: "\u0041\u0049 \u56fe\u7247\u4fee\u6539",
    readingModel: "\u6b63\u5728\u8bfb\u53d6\u56fe\u7247\u6a21\u578b",
    sourceLabel: "\u53c2\u8003\u56fe\u7247\uff08\u5df2\u4e0b\u8f7d\u6216\u672c\u5730\u4e0a\u4f20\uff09",
    clear: "\u6e05\u7a7a",
    upload: "\u4e0a\u4f20\u672c\u5730\u56fe\u7247",
    uploadHint: "\u652f\u6301 JPG\u3001PNG\u3001WebP\uff0c\u53ef\u591a\u9009\u6216\u62d6\u5230\u4e0b\u65b9\u533a\u57df",
    pickerLabel: "\u53c2\u8003\u56fe\u7247\u9009\u62e9\u533a",
    promptLabel: "\u4fee\u6539\u76ee\u6807",
    promptPlaceholder: "\u4f8b\u5982\uff1a\u4fdd\u7559\u4ea7\u54c1\u4e3b\u4f53\uff0c\u6539\u6210\u660e\u4eae\u7684\u5c45\u5bb6\u573a\u666f\uff0c\u79fb\u9664\u753b\u9762\u6587\u5b57",
    instructionsLabel: "\u8865\u5145\u8981\u6c42",
    instructionsPlaceholder: "\u6784\u56fe\u3001\u8272\u5f69\u3001\u5149\u7ebf\u548c\u7981\u6b62\u51fa\u73b0\u7684\u5143\u7d20",
    sizeLabel: "\u8f93\u51fa\u6bd4\u4f8b",
    qualityLabel: "\u56fe\u7247\u8d28\u91cf",
    standard: "\u6807\u51c6",
    detailed: "\u7cbe\u7ec6",
    high: "\u9ad8\u6e05",
    start: "\u5f00\u59cb\u4fee\u6539",
    batch: "\u6279\u91cf\u4f18\u5316",
    nineGrid: "\u751f\u6210\u4e5d\u5bab\u683c",
    output: "\u4fee\u6539\u7ed3\u679c",
    waiting: "\u7b49\u5f85\u751f\u6210",
    waitingHint: "\u9009\u62e9\u56fe\u7247\u5e76\u63d0\u4ea4\u4fee\u6539\u76ee\u6807",
};

function setText(selector, value) {
    const node = typeof selector === "string" ? document.querySelector(selector) : selector;
    if (node) node.textContent = value;
}

function applyAIImageCopy(config = null) {
    const controls = document.querySelector(".image-editor-controls");
    const output = document.querySelector(".image-editor-output");
    if (!controls || !output) return;
    setText(controls.querySelector(".pane-heading h2"), AI_IMAGE_COPY.editorTitle);
    const state = elements.aiImageEditState;
    if (state && !(config && config.image_configured)) state.textContent = AI_IMAGE_COPY.readingModel;
    setText(controls.querySelector(".field-label-row > span"), AI_IMAGE_COPY.sourceLabel);
    setText(elements.clearAIEditSelection, AI_IMAGE_COPY.clear);
    setText(elements.aiEditUploadLabel, AI_IMAGE_COPY.upload);
    setText(elements.aiEditUploadHint, AI_IMAGE_COPY.uploadHint);
    if (elements.aiEditImagePicker) elements.aiEditImagePicker.setAttribute("aria-label", AI_IMAGE_COPY.pickerLabel);
    const prompt = document.querySelector('label[for="aiEditPrompt"]');
    const instructions = document.querySelector('label[for="aiEditInstructions"]');
    const size = document.querySelector('label[for="aiEditSize"]');
    const quality = document.querySelector('label[for="aiEditQuality"]');
    setText(prompt?.querySelector("span"), AI_IMAGE_COPY.promptLabel);
    if (elements.aiEditPrompt) elements.aiEditPrompt.placeholder = AI_IMAGE_COPY.promptPlaceholder;
    setText(instructions?.querySelector("span"), AI_IMAGE_COPY.instructionsLabel);
    if (elements.aiEditInstructions) elements.aiEditInstructions.placeholder = AI_IMAGE_COPY.instructionsPlaceholder;
    setText(size?.querySelector("span"), AI_IMAGE_COPY.sizeLabel);
    setText(quality?.querySelector("span"), AI_IMAGE_COPY.qualityLabel);
    const options = elements.aiEditQuality?.options || [];
    if (options.length >= 3) {
        options[0].textContent = AI_IMAGE_COPY.standard;
        options[1].textContent = AI_IMAGE_COPY.detailed;
        options[2].textContent = AI_IMAGE_COPY.high;
    }
    setText(elements.editAIImageButton?.lastChild, AI_IMAGE_COPY.start);
    setText(elements.batchEditAIImageButton?.lastChild, AI_IMAGE_COPY.batch);
    setText(elements.nineGridButton?.lastChild, AI_IMAGE_COPY.nineGrid);
    if (elements.nineGridButton) elements.nineGridButton.title = "\u9009\u62e9 9 \u5f20\u56fe\u7247\u540e\u81ea\u52a8\u5408\u6210\u4e5d\u5bab\u683c";
    setText(output.querySelector(".output-heading > span:first-child"), AI_IMAGE_COPY.output);
    setText(elements.aiEditEmpty?.querySelector("strong"), AI_IMAGE_COPY.waiting);
    setText(elements.aiEditEmpty?.querySelector("span"), AI_IMAGE_COPY.waitingHint);
    if (elements.aiEditPreviewButton) elements.aiEditPreviewButton.title = "\u653e\u5927\u67e5\u770b\u4fee\u6539\u540e\u7684\u56fe\u7247";
    if (elements.aiEditPreview) elements.aiEditPreview.alt = "AI \u4fee\u6539\u540e\u7684\u56fe\u7247";
    setText(elements.aiEditDownload?.lastChild, "\u4e0b\u8f7d\u56fe\u7247");
    setText(elements.reuseAIEditResult?.lastChild, "\u7ee7\u7eed\u4fee\u6539");
    if (config && state) {
        state.textContent = config.image_configured
            ? `${config.image_model || "\u56fe\u7247\u6a21\u578b"} \u00b7 Codex \u672c\u5730\u4e2d\u8f6c`
            : (currentUser?.role === "admin" ? "\u5c1a\u672a\u914d\u7f6e\u56fe\u7247\u6a21\u578b\uff0c\u8bf7\u5728 AI \u8bbe\u7f6e\u4e2d\u914d\u7f6e" : "\u56fe\u7247\u6a21\u578b\u5c1a\u672a\u914d\u7f6e\uff0c\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458");
    }
}

function ensureAIEditResultsUI() {
    if (elements.aiEditBatchResult) return;
    const result = elements.aiEditResult;
    if (!result?.parentElement) return;
    const batch = document.createElement("div");
    batch.id = "aiEditBatchResult";
    batch.className = "image-edit-batch-result";
    batch.hidden = true;
    const heading = document.createElement("div");
    heading.className = "batch-result-heading";
    const title = document.createElement("strong");
    title.textContent = "\u6279\u91cf\u4f18\u5316\u7ed3\u679c";
    const progress = document.createElement("span");
    progress.id = "aiEditBatchProgress";
    heading.append(title, progress);
    const gallery = document.createElement("div");
    gallery.id = "aiEditBatchGallery";
    gallery.className = "image-edit-gallery";
    batch.append(heading, gallery);
    result.parentElement.append(batch);
    elements.aiEditBatchResult = batch;
    elements.aiEditBatchGallery = gallery;
    elements.aiEditBatchProgress = progress;
}

function syncAIEditControls() {
    const selectedCount = aiEditSelectedFiles.size;
    const busy = aiImageEditing || aiEditUploading;
    elements.aiEditSelectionCount.textContent = `${selectedCount} / 12`;
    elements.aiEditImagePicker?.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
    elements.clearAIEditSelection.disabled = busy || selectedCount === 0;
    elements.aiEditUploadButton.disabled = busy || selectedCount >= 12;
    elements.aiEditImagePicker?.setAttribute("aria-busy", String(aiEditUploading));
    elements.editAIImageButton.disabled = busy || !aiImageConfigured || selectedCount === 0 || !elements.aiEditPrompt.value.trim();
    elements.batchEditAIImageButton.disabled = busy || !aiImageConfigured || selectedCount < 2 || !elements.aiEditPrompt.value.trim();
    elements.nineGridButton.disabled = busy || selectedCount !== 9;
    setText(elements.batchEditAIImageButton.lastChild, AI_IMAGE_COPY.batch);
    setText(elements.nineGridButton.lastChild, AI_IMAGE_COPY.nineGrid);
}

function renderAIEditPicker() {
    if (!elements.aiEditImagePicker) return;
    const images = libraryItems.filter((item) => item.ai_compatible);
    elements.aiEditImagePicker.replaceChildren();
    if (!images.length) {
        const empty = document.createElement("div");
        empty.className = "picker-empty";
        empty.innerHTML = '<i data-lucide="image-up"></i>';
        const text = document.createElement("span");
        text.textContent = "\u4e0b\u8f7d\u76ee\u5f55\u4e2d\u6682\u65e0\u53ef\u7528\u56fe\u7247";
        empty.append(text);
        elements.aiEditImagePicker.append(empty);
        syncAIEditControls();
        refreshIcons();
        return;
    }
    const groups = new Map();
    images.forEach((item) => {
        const parts = item.path.split("/");
        const group = parts.length > 1 ? parts.slice(0, -1).join(" / ") : "\u6839\u76ee\u5f55";
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(item);
    });
    groups.forEach((groupItems, groupName) => {
        const heading = document.createElement("div");
        heading.className = "picker-group-title";
        heading.textContent = `${groupName} \u00b7 ${groupItems.length} \u5f20`;
        elements.aiEditImagePicker.append(heading);
        groupItems.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `picker-item${aiEditSelectedFiles.has(item.path) ? " selected" : ""}`;
            button.title = item.name;
            button.setAttribute("aria-label", `${aiEditSelectedFiles.has(item.path) ? "\u53d6\u6d88\u9009\u62e9" : "\u9009\u62e9"} ${item.name}`);
            button.setAttribute("aria-pressed", String(aiEditSelectedFiles.has(item.path)));
            button.disabled = aiEditUploading || aiImageEditing;
            const image = document.createElement("img");
            image.src = item.thumbnail_url || item.preview_url;
            image.decoding = "async";
            image.alt = item.name;
            image.loading = "lazy";
            const name = document.createElement("span");
            name.textContent = item.name;
            const check = document.createElement("i");
            check.setAttribute("data-lucide", "check");
            const remove = document.createElement("span");
            remove.className = "picker-remove";
            remove.textContent = "\u00d7";
            remove.title = "\u53d6\u6d88\u9009\u62e9";
            remove.setAttribute("role", "button");
            remove.setAttribute("tabindex", "0");
            const removeSelection = (event) => {
                event.preventDefault();
                event.stopPropagation();
                aiEditSelectedFiles.delete(item.path);
                renderAIEditPicker();
            };
            remove.addEventListener("click", removeSelection);
            remove.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") removeSelection(event);
            });
            const deleteImage = document.createElement("span");
            deleteImage.className = "picker-delete";
            deleteImage.title = "\u5220\u9664\u672c\u5730\u56fe\u7247";
            deleteImage.setAttribute("role", "button");
            deleteImage.setAttribute("tabindex", "0");
            deleteImage.setAttribute("aria-label", `\u5220\u9664 ${item.name}`);
            deleteImage.innerHTML = '<i data-lucide="trash-2"></i>';
            const deleteLocalImage = async (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (aiEditUploading || aiImageEditing || !window.confirm(`\u786e\u5b9a\u5220\u9664 ${item.name}\uff1f`)) return;
                try {
                    await api(`/api/library?path=${encodeURIComponent(item.path)}`, { method: "DELETE" });
                    aiEditSelectedFiles.delete(item.path);
                    selectedFiles.delete(item.path);
                    libraryFingerprint = "";
                    await refreshLibrary();
                    showToast("\u56fe\u7247\u5df2\u4ece\u672c\u5730\u7d20\u6750\u5e93\u5220\u9664");
                } catch (error) { showToast(error.message, true); }
            };
            deleteImage.addEventListener("click", deleteLocalImage);
            deleteImage.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") deleteLocalImage(event);
            });
            button.append(image, name, check, remove, deleteImage);
            button.addEventListener("click", () => {
                if (aiEditSelectedFiles.has(item.path)) aiEditSelectedFiles.delete(item.path);
                else if (aiEditSelectedFiles.size >= 12) showToast("\u4e00\u6b21\u6700\u591a\u9009\u62e9 12 \u5f20\u53c2\u8003\u56fe\u7247", true);
                else aiEditSelectedFiles.add(item.path);
                renderAIEditPicker();
            });
            elements.aiEditImagePicker.append(button);
        });
    });
    syncAIEditControls();
    refreshIcons();
}

function clearAIEditResult() {
    ensureAIEditResultsUI();
    elements.aiEditResult.hidden = true;
    elements.aiEditBatchResult.hidden = true;
    elements.aiEditBatchGallery.replaceChildren();
    elements.aiEditBatchProgress.textContent = "";
    elements.aiEditEmpty.hidden = false;
    elements.aiEditPreview.removeAttribute("src");
    elements.aiEditPreviewButton.dataset.path = "";
    elements.aiEditDownload.href = "#";
    elements.aiEditDownload.removeAttribute("download");
    elements.aiEditResultMeta.textContent = "";
}

function appendAIEditResultCard(item, index, total) {
    const card = document.createElement("article");
    card.className = "image-edit-card";
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "image-edit-card-preview";
    preview.title = "\u67e5\u770b\u5927\u56fe";
    const image = document.createElement("img");
    image.src = item.preview_url;
    image.alt = item.source_name ? `\u7b2c ${index + 1} \u5f20\uff1a${item.source_name}` : `\u7b2c ${index + 1} \u5f20\u4f18\u5316\u7ed3\u679c`;
    image.loading = "lazy";
    preview.append(image);
    preview.addEventListener("click", async () => {
        await refreshLibrary();
        const current = libraryItems.find((entry) => entry.path === item.path) || item;
        if (current.path) openMediaViewer(current);
    });
    const meta = document.createElement("div");
    meta.className = "image-edit-card-meta";
    const label = document.createElement("strong");
    label.textContent = item.is_grid ? "\u4e5d\u5bab\u683c" : `\u7b2c ${index + 1} \u5f20`;
    const source = document.createElement("span");
    source.textContent = item.source_name || item.name || "\u4f18\u5316\u7ed3\u679c";
    meta.append(label, source);
    const download = document.createElement("a");
    download.className = "button secondary image-edit-card-download";
    download.href = item.download_url;
    download.download = item.name || "AI-image";
    download.innerHTML = '<i data-lucide="download"></i>';
    const downloadText = document.createElement("span");
    downloadText.textContent = "\u4e0b\u8f7d";
    download.append(downloadText);
    card.append(preview, meta, download);
    return card;
}

function renderAIEditBatchResults(outputs = [], errors = [], task = {}) {
    ensureAIEditResultsUI();
    const validOutputs = Array.isArray(outputs) ? outputs : [];
    const validErrors = Array.isArray(errors) ? errors : [];
    elements.aiEditBatchGallery.replaceChildren();
    validOutputs.forEach((item, index) => {
        if (item?.preview_url && item?.download_url) elements.aiEditBatchGallery.append(appendAIEditResultCard(item, index, validOutputs.length));
    });
    validErrors.forEach((entry) => {
        const error = document.createElement("div");
        error.className = "image-edit-card-error";
        error.textContent = `${entry.path || "\u56fe\u7247"}\uff1a${entry.error || "\u5904\u7406\u5931\u8d25"}`;
        elements.aiEditBatchGallery.append(error);
    });
    const count = validOutputs.length + validErrors.length;
    elements.aiEditEmpty.hidden = count > 0;
    elements.aiEditBatchResult.hidden = count === 0;
    elements.aiEditResult.hidden = true;
    elements.aiEditBatchProgress.textContent = task.total ? `\u5df2\u5b8c\u6210 ${task.completed || count}/${task.total}` : "";
    refreshIcons();
}

const legacyRenderAIConfig = renderAIConfig;
renderAIConfig = function(config) {
    legacyRenderAIConfig(config);
    applyAIImageCopy(config);
};

const legacyGenerateAIImageEdit = generateAIImageEdit;
generateAIImageEdit = async function() {
    await legacyGenerateAIImageEdit();
    if (elements.aiEditResult.hidden) {
        elements.aiImageEditState.textContent = "\u56fe\u7247\u4fee\u6539\u5931\u8d25";
        showToast("\u56fe\u7247\u4fee\u6539\u5931\u8d25", true);
        return;
    }
    elements.aiImageEditState.textContent = `\u56fe\u7247\u4fee\u6539\u5b8c\u6210\uff0c${aiImageModelName || "\u56fe\u7247\u6a21\u578b"}`;
    elements.aiEditResultMeta.textContent = `${aiImageModelName || "\u56fe\u7247\u6a21\u578b"} \u00b7 \u5df2\u4fdd\u5b58`;
    showToast("\u56fe\u7247\u4fee\u6539\u5b8c\u6210\uff0c\u5df2\u4fdd\u5b58\u5230\u4e0b\u8f7d\u76ee\u5f55");
};

async function generateBatchAIImageEditQueued() {
    const prompt = elements.aiEditPrompt.value.trim();
    const paths = [...aiEditSelectedFiles];
    if (paths.length < 2 || !prompt) return;
    aiImageEditing = true;
    syncAIEditControls();
    clearAIEditResult();
    elements.aiImageEditState.textContent = `\u6b63\u5728\u63d0\u4ea4 ${paths.length} \u5f20\u56fe\u7247`;
    let task = null;
    try {
        const result = await api("/api/ai/images/edit/batch", {
            method: "POST",
            body: JSON.stringify({ image_paths: paths, prompt, instructions: elements.aiEditInstructions.value.trim(), image_size: elements.aiEditSize.value, image_quality: elements.aiEditQuality.value }),
        });
        const taskId = result.task?.task_id;
        if (!taskId) throw new Error("\u6279\u91cf\u4efb\u52a1\u521b\u5efa\u5931\u8d25");
        task = result.task;
        renderAIEditBatchResults(task.outputs, task.errors, task);
        for (let attempt = 0; attempt < 600; attempt += 1) {
            const status = await api("/api/ai/images/edit/batch-status");
            task = status.tasks.find((item) => item.task_id === taskId) || task;
            renderAIEditBatchResults(task.outputs, task.errors, task);
            const liveOutputs = Array.isArray(task.outputs) ? task.outputs.length : 0;
            const liveErrors = Array.isArray(task.errors) ? task.errors.length : 0;
            elements.aiEditResultMeta.textContent = `${task.image_model || "\u56fe\u7247\u6a21\u578b"} \u00b7 ${liveOutputs} \u5f20\u7ed3\u679c${liveErrors ? `\uff0c${liveErrors} \u5f20\u5931\u8d25` : ""}`;
            if (["success", "partial", "failed"].includes(task.state)) break;
            elements.aiImageEditState.textContent = `\u6b63\u5728\u9010\u5f20\u751f\u6210\uff1a${task.completed || 0}/${task.total || paths.length}`;
            await new Promise((resolve) => setTimeout(resolve, 800));
        }
        const outputs = task.outputs || [];
        const errors = task.errors || [];
        const gridDetail = task.nine_grid ? "\uff0c\u4e5d\u5bab\u683c\u5df2\u81ea\u52a8\u751f\u6210" : "";
        elements.aiImageEditState.textContent = task.state === "failed"
            ? "\u6279\u91cf\u4fee\u6539\u5931\u8d25"
            : `\u6279\u91cf\u5b8c\u6210\uff1a${outputs.length} \u5f20${gridDetail}`;
        elements.aiEditResultMeta.textContent = `${task.image_model || "\u56fe\u7247\u6a21\u578b"} \u00b7 ${outputs.length} \u5f20\u7ed3\u679c${errors.length ? `\uff0c${errors.length} \u5f20\u5931\u8d25` : ""}`;
        renderAIEditBatchResults(outputs, errors, task);
        if (task.nine_grid) {
            elements.aiEditBatchGallery.append(appendAIEditResultCard({ ...task.nine_grid, source_name: "\u4e5d\u5bab\u683c", is_grid: true }, outputs.length, outputs.length + 1));
        }
        historyLoaded = false;
        await loadBilling();
        await refreshLibrary();
        showToast(`\u5df2\u5b8c\u6210 ${outputs.length} \u5f20\u56fe\u7247\u4f18\u5316${errors.length ? `\uff0c${errors.length} \u5f20\u5931\u8d25` : ""}`);
    } catch (error) {
        elements.aiImageEditState.textContent = "\u6279\u91cf\u4fee\u6539\u5931\u8d25";
        showToast(error.message, true);
    } finally {
        aiImageEditing = false;
        syncAIEditControls();
    }
}

applyAIImageCopy();

elements.pasteButton.addEventListener("click", pasteLink);
elements.clearInputButton.addEventListener("click", () => { elements.urlInput.value = ""; elements.urlInput.focus(); });
elements.downloadButton.addEventListener("click", createDownload);
elements.urlInput.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") createDownload(); });
elements.clearTasksButton.addEventListener("click", async () => { try { await api("/api/tasks", { method: "DELETE" }); await refreshState(); } catch (error) { showToast(error.message, true); } });
elements.fileSearch.addEventListener("input", renderLibrary);
elements.refreshLibraryButton.addEventListener("click", refreshLibrary);
elements.alibabaCollect.addEventListener("click", collectAlibabaProducts);
elements.xhsProductCollect.addEventListener("click", collectXhsProducts);
document.querySelectorAll("[data-product-tab]").forEach((tab) => tab.addEventListener("click", () => { window.location.hash = `products/${tab.dataset.productTab}`; }));
elements.copyViewerImage.addEventListener("click", () => copyProductImage(viewerItems[currentMediaIndex]?.copy_url));
elements.optimizeViewerImage.addEventListener("click", () => importProductForAI(viewerItems[currentMediaIndex]?.import_url));
elements.selectAllFiles.addEventListener("change", () => {
    filteredLibrary().forEach((item) => { if (elements.selectAllFiles.checked) selectedFiles.add(item.path); else selectedFiles.delete(item.path); });
    renderLibrary();
});
elements.enhanceButton.addEventListener("click", createEnhancement);
elements.livePhotoButton.addEventListener("click", openLivePhotoEditor);
window.addEventListener("open-live-photo-editor", (event) => {
    const source = event.detail;
    if (!source?.path || source.media_kind !== "image") return;
    openLivePhotoEditor(source);
});
elements.livePhotoForm.addEventListener("submit", createLivePhoto);
elements.livePhotoVideo.addEventListener("loadedmetadata", syncLivePhotoControls);
elements.liveMotionMode.addEventListener("change", syncLivePhotoControls);
elements.liveStartRange.addEventListener("input", () => {
    syncLivePhotoControls();
    if (Number.isFinite(elements.livePhotoVideo.duration)) elements.livePhotoVideo.currentTime = Number(elements.liveStartRange.value);
});
elements.liveDurationRange.addEventListener("input", syncLivePhotoControls);
elements.livePhotoDialog.addEventListener("close", resetLivePhotoEditor);
elements.livePhotoDialog.addEventListener("click", (event) => { if (event.target === elements.livePhotoDialog) elements.livePhotoDialog.close(); });
elements.batchEditAIImageButton.addEventListener("click", generateBatchAIImageEditQueued);
elements.nineGridButton.addEventListener("click", generateNineGrid);
elements.remixButton.addEventListener("click", createVideoRemix);
elements.dedupeButton.addEventListener("click", findVideoDuplicates);
elements.slideshowButton.addEventListener("click", openSlideshowDialog);
elements.archiveButton.addEventListener("click", downloadArchive);
elements.deleteSelectedButton?.addEventListener("click", async () => {
    if (!selectedFiles.size || !confirm(`确定删除选中的 ${selectedFiles.size} 个文件？`)) return;
    const paths = [...selectedFiles];
    try {
        await Promise.all(paths.map((path) => api(`/api/library?path=${encodeURIComponent(path)}`, { method: "DELETE" })));
        selectedFiles.clear(); await refreshLibrary(); showToast(`已删除 ${paths.length} 个文件`);
    } catch (error) { showToast(error.message, true); }
});
elements.aiGenerationModes.forEach((input) => input.addEventListener("change", syncAIGenerationMode));
elements.aiCopywritingMode.addEventListener("change", syncCopywritingMode);
elements.generateAIButton.addEventListener("click", generateAIContent);
elements.refreshHistoryButton.addEventListener("click", () => {
    historyLoaded = false;
    loadHistory().catch((error) => showToast(error.message, true));
});
elements.historyLoadMore.addEventListener("click", () => loadHistory(true).catch((error) => showToast(error.message, true)));
elements.historySearch.addEventListener("input", () => {
    clearTimeout(historySearchTimer);
    historySearchTimer = setTimeout(() => {
        historyLoaded = false;
        loadHistory().catch((error) => showToast(error.message, true));
    }, 250);
});
elements.reuseHistoryButton.addEventListener("click", reuseHistory);
elements.copyHistoryButton.addEventListener("click", () => copyHistoryOutput().catch((error) => showToast(error.message, true)));
elements.deleteHistoryButton.addEventListener("click", () => deleteHistory().catch((error) => showToast(error.message, true)));
elements.refreshCorpusButton.addEventListener("click", () => {
    corpusLoaded = false;
    loadCorpus().catch((error) => showToast(error.message, true));
});
elements.corpusLoadMore.addEventListener("click", () => loadCorpus(true).catch((error) => showToast(error.message, true)));
elements.corpusSearch.addEventListener("input", () => {
    clearTimeout(corpusSearchTimer);
    corpusSearchTimer = setTimeout(() => {
        corpusLoaded = false;
        loadCorpus().catch((error) => showToast(error.message, true));
    }, 250);
});
elements.useCorpusButton.addEventListener("click", useCorpusForCreation);
elements.aiEditPrompt.addEventListener("input", syncAIEditControls);
elements.editAIImageButton.addEventListener("click", generateAIImageEdit);
elements.aiEditUploadButton.addEventListener("click", () => elements.aiEditUploadInput.click());
elements.aiEditUploadInput.addEventListener("change", () => uploadAIEditImages(elements.aiEditUploadInput.files));
["dragenter", "dragover"].forEach((eventName) => {
    elements.aiEditImagePicker.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        elements.aiEditImagePicker.classList.add("drag-over");
    });
});
["dragleave", "drop"].forEach((eventName) => {
    elements.aiEditImagePicker.addEventListener(eventName, (event) => {
        event.preventDefault();
        elements.aiEditImagePicker.classList.remove("drag-over");
        if (eventName === "drop") uploadAIEditImages(event.dataTransfer.files);
    });
});
elements.clearAIEditSelection.addEventListener("click", () => {
    aiEditSelectedFiles.clear();
    renderAIEditPicker();
});
elements.aiEditPreviewButton.addEventListener("click", async () => {
    const path = elements.aiEditPreviewButton.dataset.path;
    if (!path) return;
    await refreshLibrary();
    const item = libraryItems.find((entry) => entry.path === path);
    if (item) openMediaViewer(item);
});
elements.reuseAIEditResult.addEventListener("click", () => {
    const path = elements.aiEditPreviewButton.dataset.path;
    if (!path) return;
    aiEditSelectedFiles = new Set([path]);
    renderAIEditPicker();
    elements.aiEditPrompt.focus();
});
elements.generationFeedback.addEventListener("submit", submitGenerationFeedback);
elements.copyAIOutputButton.addEventListener("click", () => {
    copyAIOutput().catch((error) => showToast(error.message, true));
});
elements.clearAIOutputButton.addEventListener("click", () => {
    elements.aiOutput.value = "";
    elements.copyAIOutputButton.disabled = true;
    clearGeneratedImage();
    clearGenerationFeedback();
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
elements.mediaViewerImage.addEventListener("error", () => {
    if (elements.mediaViewerImage.hasAttribute("src")) elements.mediaViewerMeta.textContent = "图片加载失败，请关闭后重试或下载原文件";
});
elements.mediaViewerVideo.addEventListener("error", () => {
    if (elements.mediaViewerVideo.hasAttribute("src")) elements.mediaViewerMeta.textContent = "视频加载失败或格式不受支持，请下载原文件";
});
elements.closeMediaViewerButton.addEventListener("click", () => elements.mediaViewerDialog.close());
elements.mediaViewerImage.addEventListener("click", () => {
    const zoomed = elements.mediaViewerImage.classList.toggle("zoomed");
    elements.mediaStage.classList.toggle("zoom-active", zoomed);
    if (!zoomed) elements.mediaStage.scrollTo(0, 0);
});
elements.mediaViewerDialog.addEventListener("close", () => {
    resetMediaViewer();
    currentMediaIndex = -1;
    viewerItems = [];
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
    if (event.submitter?.id !== "saveCookieButton") return;
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
syncCopywritingMode();
activateRoute();
clearAIEditResult();
refreshIcons();
window.operationBridge = {
    api,
    openImageEditor: async (item) => { await refreshLibrary(); openAIImageEditor(item); },
    showToast,
    refreshIcons,
    currentUser: () => currentUser,
    navigateTo,
};
bootstrapAuthentication();
