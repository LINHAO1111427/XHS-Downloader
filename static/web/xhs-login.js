(() => {
    const start = document.getElementById("xhsScanLogin");
    const cancel = document.getElementById("xhsCancelLogin");
    const status = document.getElementById("xhsLoginStatus");
    const manual = document.getElementById("saveCookieButton");
    const input = document.getElementById("cookieInput");
    const active = new Set(["opening", "waiting", "verifying", "saving"]);
    let timer = null;
    let loading = false;
    let announced = false;

    function render(result) {
        const running = active.has(result.state);
        start.hidden = serverMode;
        start.disabled = serverMode || running || currentUser?.role !== "admin";
        cancel.hidden = !running;
        manual.disabled = running || (!serverMode && currentUser?.role !== "admin");
        input.disabled = running;
        status.textContent = serverMode ? "填写你自己的小红书 Cookie，仅用于你的工作区" : result.message;
        if (running && !timer) timer = setInterval(refresh, 1200);
        if (!running) { clearInterval(timer); timer = null; }
        if (result.state === "success" && !announced) {
            announced = true;
            input.value = "";
            document.getElementById("cookieState").textContent = "已通过扫码登录配置";
            showToast("小红书登录成功，已自动保存，可立即采集");
            refreshState().catch(() => {});
        }
    }

    async function refresh() {
        if (loading) return;
        if (!serverMode && currentUser?.role !== "admin") {
            clearInterval(timer); timer = null;
            start.disabled = true; manual.disabled = true; cancel.hidden = true;
            status.textContent = "请使用超级管理员账号配置小红书登录";
            return;
        }
        loading = true;
        try { render(await api("/api/xhs/login")); }
        catch (error) { status.textContent = error.message; clearInterval(timer); timer = null; }
        finally { loading = false; }
    }

    start.addEventListener("click", async () => {
        start.disabled = true;
        announced = false;
        try { render(await api("/api/xhs/login", { method: "POST" })); }
        catch (error) { status.textContent = error.message; start.disabled = currentUser?.role !== "admin"; }
    });
    cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try { render(await api("/api/xhs/login", { method: "DELETE" })); }
        catch (error) { status.textContent = error.message; }
        finally { cancel.disabled = false; }
    });
    document.getElementById("settingsButton").addEventListener("click", refresh);
})();
