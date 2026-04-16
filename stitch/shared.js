(function () {
  const STORAGE_KEY = "brewgram.mobile.state.v1";
  const CLIENT_ID_STORAGE_KEY = "brewgram.mobile.client-id.v1";
  const SESSION_ID_STORAGE_KEY = "brewgram.mobile.session-id.v1";
  const PAGE = document.body.dataset.stitchPage;
  const API_BASE = "/api/mobile";
  const MAX_HISTORY_ITEMS = 12;
  const PATHS = {
    welcome: "/stitch/welcome.html",
    home: "/stitch/index.html",
    archive: "/stitch/archive.html",
    settings: "/stitch/settings.html",
    create: "/stitch/4._2/code.html",
    onboarding1: "/stitch/1./code.html",
    onboarding2: "/stitch/2./code.html",
    onboarding3: "/stitch/3./code.html",
    onboarding4: "/stitch/onboarding-instagram.html",
  };
  const PRESET_GOALS = ["신제품 출시", "브랜드 인지도", "이벤트 홍보", "매장 방문 유도"];
  const NEW_PRODUCT_GOAL_PREFIX = "신제품 출시";

  const defaultState = {
    onboarding: {
      brandName: "",
      brandColor: "#ff7448",
      brandAtmosphere: "",
      brandDescription: "",
      instagramUrl: "",
      logo: null,
      referenceImages: [],
      analysisContent: "",
    },
    create: {
      productName: "",
      productDescription: "",
      goal: "브랜드 인지도",
      generationType: "both",
      tone: "감성",
      style: "감성",
      productImage: null,
      referenceUrl: "",
      referenceImage: null,
      isNewProduct: false,
      selectedProductName: "",
      selectedProductImageUrl: null,
    },
    preferences: {
      notificationsEnabled: true,
      uploadPlaceholderEnabled: true,
      defaultTone: "감성",
      defaultStyle: "감성",
    },
    history: [],
    meta: {
      lastHistoryId: null,
    },
  };

  let lastGenerateResult = null;
  let lastCaptionResult = null;
  let lastStoryResult = null;
  let lastBootstrap = null;
  let deferredInstallPrompt = null;
  let memoryClientId = null;
  let memorySessionId = null;

  function cloneDefaults() {
    return JSON.parse(JSON.stringify(defaultState));
  }

  function readState() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return cloneDefaults();
      }
      return deepMerge(cloneDefaults(), JSON.parse(raw));
    } catch (_) {
      return cloneDefaults();
    }
  }

  function writeState(nextState) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
    return nextState;
  }

  function patchState(patch) {
    const next = deepMerge(readState(), patch);
    return writeState(next);
  }

  function deepMerge(target, source) {
    if (!source || typeof source !== "object") {
      return target;
    }
    for (const [key, value] of Object.entries(source)) {
      if (
        value &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        target[key] &&
        typeof target[key] === "object" &&
        !Array.isArray(target[key])
      ) {
        deepMerge(target[key], value);
      } else {
        target[key] = value;
      }
    }
    return target;
  }

  function generateId() {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID();
    }

    const bytes = new Uint8Array(16);
    if (window.crypto?.getRandomValues) {
      window.crypto.getRandomValues(bytes);
    } else {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = Math.floor(Math.random() * 256);
      }
    }

    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;

    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
    return [
      hex.slice(0, 8),
      hex.slice(8, 12),
      hex.slice(12, 16),
      hex.slice(16, 20),
      hex.slice(20),
    ].join("-");
  }

  function safeReadStorage(storage, key) {
    try {
      return storage.getItem(key);
    } catch (_) {
      return null;
    }
  }

  function safeWriteStorage(storage, key, value) {
    try {
      storage.setItem(key, value);
    } catch (_) {
      // 일부 브라우저/모드에서는 storage 접근이 막힐 수 있다.
    }
    return value;
  }

  function getClientId() {
    const stored = safeReadStorage(window.localStorage, CLIENT_ID_STORAGE_KEY) || memoryClientId;
    if (stored) {
      memoryClientId = stored;
      return stored;
    }

    const nextId = generateId();
    memoryClientId = nextId;
    return safeWriteStorage(window.localStorage, CLIENT_ID_STORAGE_KEY, nextId);
  }

  function getSessionId() {
    const stored = safeReadStorage(window.sessionStorage, SESSION_ID_STORAGE_KEY) || memorySessionId;
    if (stored) {
      memorySessionId = stored;
      return stored;
    }

    const nextId = generateId();
    memorySessionId = nextId;
    return safeWriteStorage(window.sessionStorage, SESSION_ID_STORAGE_KEY, nextId);
  }

  function buildTraceHeaders() {
    return {
      "X-Brewgram-Client-Id": getClientId(),
      "X-Brewgram-Session-Id": getSessionId(),
      "X-Brewgram-Page": PAGE || "unknown",
      "X-Brewgram-Install-State": getPwaInstallState(),
    };
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...buildTraceHeaders(),
        ...(options.headers || {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "요청 처리 중 오류가 발생했습니다.");
    }
    return data;
  }

  function setStatus(node, message, tone = "neutral") {
    if (!node) return;
    if (!message) {
      node.classList.add("hidden");
      node.textContent = "";
      return;
    }

    const toneClassMap = {
      neutral: "stitch-status--neutral",
      loading: "stitch-status--loading",
      success: "stitch-status--success",
      error: "stitch-status--error",
    };

    node.className = `stitch-status ${toneClassMap[tone] || toneClassMap.neutral}`;
    node.textContent = message;
    node.classList.remove("hidden");
  }

  function toggleTokens(element, tokens, enabled) {
    if (!tokens || !element) return;
    tokens
      .split(/\s+/)
      .filter(Boolean)
      .forEach((token) => element.classList.toggle(token, enabled));
  }

  function selectOne(selector) {
    return document.querySelector(selector);
  }

  function selectAll(selector) {
    return Array.from(document.querySelectorAll(selector));
  }

  function navigate(path) {
    window.location.href = path;
  }

  function isStandaloneDisplay() {
    return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  }

  function isIOSDevice() {
    return /iphone|ipad|ipod/i.test(window.navigator.userAgent || "");
  }

  function getPwaInstallState() {
    if (isStandaloneDisplay()) {
      return "installed";
    }
    if (deferredInstallPrompt) {
      return "available";
    }
    if (isIOSDevice()) {
      return "ios_manual";
    }
    if (window.isSecureContext) {
      return "manual";
    }
    return "unsupported";
  }

  function notifyPwaInstallStatusChange() {
    window.dispatchEvent(
      new CustomEvent("brewgram:pwa-install-state", {
        detail: { state: getPwaInstallState() },
      }),
    );
  }

  async function registerPwaServiceWorker() {
    if (!("serviceWorker" in navigator)) {
      notifyPwaInstallStatusChange();
      return;
    }
    try {
      await navigator.serviceWorker.register("/stitch/service-worker.js", { scope: "/stitch/" });
    } catch (_) {
      // Installation still works without SW on some platforms, but offline caching won't.
    }
    notifyPwaInstallStatusChange();
  }

  function clearQueryFromCurrentPath() {
    window.history.replaceState({}, "", window.location.pathname);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => {
      const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return map[character] || character;
    });
  }

  function formatHistoryTimestamp(isoString) {
    if (!isoString) return "방금";
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "방금";
    const now = new Date();
    const timeLabel = new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
    const isToday =
      now.getFullYear() === date.getFullYear() &&
      now.getMonth() === date.getMonth() &&
      now.getDate() === date.getDate();
    if (isToday) {
      return `오늘 ${timeLabel}`;
    }
    return new Intl.DateTimeFormat("ko-KR", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function parseInstagramHandle(rawUrl, fallbackLabel) {
    if (rawUrl) {
      const match = rawUrl.match(/instagram\.com\/([^/?#]+)/i);
      if (match?.[1]) {
        return match[1].replace(/^@/, "");
      }
    }
    return String(fallbackLabel || "brewgram")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_가-힣]/g, "")
      .slice(0, 20) || "brewgram";
  }

  function getInstagramSummary(bootstrapLike) {
    return (
      bootstrapLike?.instagram || {
        oauth_available: false,
        connect_available: true,
        connected: false,
        expired: false,
        upload_ready: false,
        connection_source: "none",
        username: null,
        page_name: null,
        expires_at: null,
      }
    );
  }

  function instagramStatusLabel(summary) {
    if (summary.connected && summary.username) {
      return `@${summary.username}`;
    }
    if (summary.connected) {
      return "연결됨";
    }
    if (summary.expired) {
      return "재연결 필요";
    }
    if (summary.connection_source === "env") {
      return "기본 업로드 계정 사용 중";
    }
    if (summary.oauth_available) {
      return "미연결";
    }
    if (summary.connect_available) {
      return "연결 안내 준비";
    }
    return "설정 필요";
  }

  function instagramStatusCopy(summary, onboardingCompleted = true) {
    if (!onboardingCompleted) {
      return "브랜드 온보딩을 먼저 완료해야 사장님 계정을 연결할 수 있습니다.";
    }
    if (summary.connected) {
      const handle = summary.username ? `@${summary.username}` : "연결된 계정";
      return `${handle} 계정이 연결되어 있습니다. 이후 자동 업로드 기능이 붙으면 이 계정으로 바로 게시됩니다.`;
    }
    if (summary.expired) {
      return "이전 연결이 만료되었습니다. 다시 연결하면 이후 업로드 흐름에 그대로 이어붙일 수 있습니다.";
    }
    if (summary.connection_source === "env") {
      return "현재는 기본 업로드 계정만 연결되어 있습니다. 사장님 계정을 직접 연결하려면 Meta 로그인 설정이 필요합니다.";
    }
    if (summary.oauth_available) {
      return "사장님 본인 계정을 한 번만 연결해두면 이후 피드와 스토리를 바로 업로드할 수 있습니다.";
    }
    if (summary.connect_available) {
      return "연결 흐름과 API는 준비되어 있습니다. Meta 앱 설정만 붙이면 지금 버튼으로 실제 연결을 바로 시작할 수 있습니다.";
    }
    return "현재 환경에서는 Meta 로그인 설정이 없어 사장님 계정 연결을 시작할 수 없습니다.";
  }

  function instagramSettingsNote(summary, onboardingCompleted = true) {
    if (!onboardingCompleted) {
      return "브랜드 정보를 저장한 뒤 계정을 연결하면 결과 화면의 업로드 버튼과 자연스럽게 이어집니다.";
    }
    if (summary.connected) {
      return "계정 연결은 완료되었습니다. 자동 업로드 API만 붙이면 지금 배치된 업로드 버튼이 이 계정을 바로 사용합니다.";
    }
    if (summary.expired) {
      return "만료 후에는 다시 연결만 하면 됩니다. 저장된 UI 흐름이나 생성 결과는 그대로 유지됩니다.";
    }
    if (summary.oauth_available) {
      return "이 화면에서 연결과 재연결을 관리합니다. 한번 연결해두면 이후 업로드 버튼이 같은 계정을 사용합니다.";
    }
    if (summary.connect_available) {
      return "버튼과 API는 준비되어 있습니다. Meta 앱 설정만 연결되면 이 버튼이 바로 실제 로그인 화면으로 이어집니다.";
    }
    return "현재 환경에서는 사장님 계정 연결을 사용할 수 없습니다.";
  }

  function instagramGuideCopy(summary) {
    if (summary.connected) {
      const handle = summary.username ? `@${summary.username}` : "연결된 계정";
      return `${handle} 계정이 연결되어 있어요. 자동 업로드 API만 붙이면 지금 업로드 버튼이 바로 이 계정으로 이어집니다.`;
    }
    if (summary.expired) {
      return "이전 인스타그램 연결이 만료되었습니다. 설정에서 다시 연결해두면 이후 자동 업로드 흐름을 자연스럽게 붙일 수 있습니다.";
    }
    if (summary.connection_source === "env") {
      return "현재는 기본 업로드 계정으로만 게시할 수 있습니다. 사장님 계정 직접 연결은 설정에서 시작합니다.";
    }
    if (summary.oauth_available) {
      return "사장님 계정을 한 번 연결해두면, 이후 피드와 스토리를 바로 업로드할 수 있습니다.";
    }
    if (summary.connect_available) {
      return "연결 UI와 API는 준비되어 있습니다. Meta 앱 설정만 붙이면 바로 실제 연결을 시작할 수 있습니다.";
    }
    return "자동 업로드는 다음 단계에서 연결합니다. 지금은 저장 버튼과 인스타그램 미리보기 중심으로 결과를 점검하면 됩니다.";
  }

  function buildUploadPlaceholder(summary, kind) {
    const target = kind === "story" ? "스토리" : "피드";
    if (summary.expired) {
      return {
        tone: "neutral",
        html: `이전 인스타그램 연결이 만료되었습니다. <a href="${PATHS.settings}">설정에서 다시 연결</a>한 뒤 ${target} 업로드를 이어갈 수 있습니다.`,
        status: "인스타그램 연결이 만료되어 다시 연결이 필요합니다.",
      };
    }
    if (!summary.upload_ready) {
      return {
        tone: "neutral",
        html: `자동 ${target} 업로드를 쓰려면 먼저 인스타그램 계정을 연결해주세요. <a href="${PATHS.settings}">설정에서 연결하기</a>`,
        status: "인스타그램 계정을 먼저 연결해야 합니다.",
      };
    }
    if (summary.connected) {
      const handle = summary.username ? `@${escapeHtml(summary.username)}` : "연결된 계정";
      return {
        tone: "neutral",
        html: `${handle} 계정이 연결되어 있습니다. 아래 ${target} 업로드 버튼을 누르면 바로 게시를 시도합니다.`,
        status: `${target} 업로드 준비가 완료되었습니다.`,
      };
    }
    return {
      tone: "neutral",
      html: `현재는 기본 업로드 계정으로 ${target} 업로드를 시도합니다. 사장님 계정으로 바로 올리려면 <a href="${PATHS.settings}">설정에서 Meta 계정 연결</a>을 먼저 진행해 주세요.`,
      status: `${target} 업로드 준비가 완료되었습니다.`,
    };
  }

  function buildFeedUploadCaption(result, captionResult, state) {
    if (captionResult?.caption) {
      return `${captionResult.caption}\n\n${captionResult.hashtags || ""}`.trim();
    }
    const fallbackCopy =
      result?.text_result?.ad_copies?.[0] ||
      result?.text_result?.promo_sentences?.[0] ||
      `${state.create.productName} 홍보 문구`;
    return fallbackCopy.trim();
  }

  function applyUploadButtonState() {
    const uploadFeedButton = selectOne("#create-upload-feed-button");
    const uploadStoryButton = selectOne("#create-upload-story-button");
    const hasFeedImage = Boolean(lastGenerateResult?.image_data_url);
    const hasStoryImage = Boolean(lastStoryResult?.image_data_url);

    if (uploadFeedButton) {
      uploadFeedButton.disabled = !hasFeedImage;
      uploadFeedButton.classList.toggle("action-button--disabled", !hasFeedImage);
    }
    if (uploadStoryButton) {
      uploadStoryButton.disabled = !hasStoryImage;
      uploadStoryButton.classList.toggle("action-button--disabled", !hasStoryImage);
    }
  }

  function consumeInstagramFeedback() {
    const params = new URLSearchParams(window.location.search);
    const flag = params.get("ig");
    if (!flag) return null;

    const message = params.get("ig_message");
    clearQueryFromCurrentPath();

    if (flag === "connected") {
      return {
        flag,
        tone: "success",
        message: "인스타그램 계정 연결이 완료되었습니다.",
      };
    }
    if (flag === "cancelled") {
      return {
        flag,
        tone: "neutral",
        message: "인스타그램 계정 연결이 취소되었습니다.",
      };
    }
    if (flag === "page_required") {
      return {
        flag,
        tone: "error",
        message:
          message ||
          "Facebook Page 연결이 필요합니다. 아래 안내를 따라 연결한 뒤 다시 시도해 주세요.",
      };
    }
    if (flag === "select_required") {
      return {
        flag,
        tone: "neutral",
        message: "연결된 Instagram 계정이 여러 개 발견되었습니다. 아래에서 사용할 계정을 선택해주세요.",
      };
    }
    if (flag === "manual_required") {
      return {
        flag,
        tone: "neutral",
        message: "Instagram professional account를 찾지 못했습니다. 아래에서 계정 ID를 직접 입력해주세요.",
      };
    }
    return {
      flag,
      tone: "error",
      message: message || "인스타그램 계정 연결 중 오류가 발생했습니다.",
    };
  }

  function setInstagramPageGuide(rootSelector, feedback) {
    const guideNode = selectOne(rootSelector);
    if (!guideNode) return;

    const copyNode = guideNode.querySelector("[id$='page-guide-copy']");
    const shouldShow = Boolean(feedback?.flag === "page_required");
    guideNode.classList.toggle("hidden", !shouldShow);

    if (shouldShow && copyNode) {
      copyNode.textContent = feedback.message;
    }
  }

  function productThumb(productName) {
    const name = String(productName || "").toLowerCase();
    if (/(coffee|커피|아메리카노|라떼|에스프레소)/.test(name)) return "☕";
    if (/(croissant|크루아상|빵|식빵|베이글)/.test(name)) return "🥐";
    if (/(cake|케이크|티라미수|디저트)/.test(name)) return "🍰";
    if (/(cookie|쿠키)/.test(name)) return "🍪";
    if (/(muffin|머핀)/.test(name)) return "🧁";
    return "✨";
  }

  function isNewProductGoal(goal) {
    return String(goal || "")
      .trim()
      .startsWith(NEW_PRODUCT_GOAL_PREFIX);
  }

  function buildHistoryEntry(createState, result) {
    const copies = result.text_result?.ad_copies || [];
    return {
      id: `hist_${Date.now()}`,
      generationId: result.generation_id || null,
      generationOutputId: result.generation_output_id || null,
      productName: createState.productName.trim(),
      goal: createState.goal,
      generationType: createState.generationType,
      tone: createState.tone,
      style: createState.style,
      createdAt: new Date().toISOString(),
      summary:
        copies[0] ||
        createState.productDescription ||
        `${createState.goal}용 ${createState.productName} 홍보 초안`,
      thumb: productThumb(createState.productName),
      imageReady: Boolean(result.image_data_url),
      captionReady: false,
      storyReady: false,
      uploadFeedStatus: "idle",
      uploadStoryStatus: "idle",
    };
  }

  function saveHistoryEntry(createState, result) {
    const state = readState();
    const entry = buildHistoryEntry(createState, result);
    const nextState = {
      ...state,
      history: [entry, ...state.history].slice(0, MAX_HISTORY_ITEMS),
      meta: {
        ...state.meta,
        lastHistoryId: entry.id,
      },
    };
    writeState(nextState);
    return entry;
  }

  function updateLastHistory(patch) {
    const state = readState();
    const targetId = state.meta?.lastHistoryId;
    if (!targetId) return;

    const nextHistory = state.history.map((item) =>
      item.id === targetId ? { ...item, ...patch } : item,
    );
    writeState({
      ...state,
      history: nextHistory,
    });
  }

  function renderEmptyState(title, copy, buttonHref, buttonLabel) {
    return `
      <div class="empty-state">
        <div class="empty-state__icon">
          <span class="material-symbols-outlined">auto_awesome</span>
        </div>
        <p class="empty-state__title">${escapeHtml(title)}</p>
        <p class="empty-state__copy">${escapeHtml(copy)}</p>
        ${
          buttonHref && buttonLabel
            ? `<a class="soft-button" style="margin-top:1rem;" href="${escapeHtml(buttonHref)}">${escapeHtml(buttonLabel)}</a>`
            : ""
        }
      </div>
    `;
  }

  function renderHistoryList(node, items, emptyOptions = {}) {
    if (!node) return;
    if (!items.length) {
      node.innerHTML = renderEmptyState(
        emptyOptions.title || "아직 만든 홍보물이 없어요",
        emptyOptions.copy || "첫 홍보물을 만들면 여기에 최근 작업이 차곡차곡 쌓입니다.",
        emptyOptions.href || PATHS.create,
        emptyOptions.label || "지금 만들기",
      );
      return;
    }

    node.innerHTML = items
      .map((item) => {
        const badges = [
          item.goal,
          item.captionReady ? "캡션 완료" : null,
          item.storyReady ? "스토리 완료" : null,
          item.uploadFeedStatus === "placeholder" ? "피드 업로드 준비" : null,
          item.uploadFeedStatus === "posted" ? "피드 게시 완료" : null,
          item.uploadStoryStatus === "placeholder" ? "스토리 업로드 준비" : null,
          item.uploadStoryStatus === "posted" ? "스토리 게시 완료" : null,
        ].filter(Boolean);
        const status =
          item.uploadFeedStatus === "posted" || item.uploadStoryStatus === "posted"
            ? "게시 완료"
            : item.uploadFeedStatus === "placeholder" || item.uploadStoryStatus === "placeholder"
            ? "준비 중"
            : "생성 완료";

        return `
          <article class="history-item">
            <div class="history-thumb">${escapeHtml(item.thumb || "✨")}</div>
            <div class="history-body">
              <p class="history-title">${escapeHtml(item.productName || "이름 없는 홍보물")}</p>
              <p class="history-meta">${escapeHtml(formatHistoryTimestamp(item.createdAt))} · ${escapeHtml(item.summary || "생성된 결과 요약")}</p>
              <div class="history-badges">
                ${badges
                  .slice(0, 4)
                  .map((badge) => `<span class="history-badge">${escapeHtml(badge)}</span>`)
                  .join("")}
              </div>
            </div>
            <div class="history-status">${escapeHtml(status)}</div>
          </article>
        `;
      })
      .join("");
  }

  async function fileToPayload(file) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    return {
      name: file.name,
      data_url: dataUrl,
    };
  }

  function highlightChoice(buttons, activeValue, classMap) {
    buttons.forEach((button) => {
      const isActive = button.dataset.value === activeValue;
      toggleTokens(button, classMap.active, isActive);
      toggleTokens(button, classMap.inactive, !isActive);
      toggleTokens(button, classMap.activeText, isActive);
      toggleTokens(button, classMap.inactiveText, !isActive);
    });
  }

  function applyToggleState(button, isOn) {
    if (!button) return;
    button.classList.toggle("on", isOn);
    button.setAttribute("aria-pressed", String(isOn));
  }

  function parseMoodKeywords(value) {
    return String(value || "")
      .split(/[,，\n]/)
      .map((keyword) => keyword.replace(/^#/, "").trim())
      .filter(Boolean);
  }

  function formatMoodKeywords(keywords) {
    return Array.from(new Set(keywords)).join(", ");
  }

  function bindStep1() {
    const state = readState();
    const brandNameInput = selectOne("#brand-name-input");
    const atmosphereInput = selectOne("#brand-atmosphere-input");
    const moodButtons = selectAll("[data-mood-chip]");
    const colorButtons = selectAll("[data-brand-color]");
    const customColorInput = selectOne("#brand-color-custom-input");
    const customColorTrigger = selectOne("#brand-color-custom-trigger");
    const logoInput = selectOne("#brand-logo-input");
    const logoTrigger = selectOne("#brand-logo-trigger");
    const logoName = selectOne("#brand-logo-name");

    brandNameInput.value = state.onboarding.brandName || "";
    atmosphereInput.value = state.onboarding.brandAtmosphere || "";

    const setActiveColor = (value) => {
      colorButtons.forEach((button) => {
        const isActive = button.dataset.brandColor === value;
        const swatch = button.querySelector("div");
        swatch?.classList.toggle("ring-2", isActive);
        swatch?.classList.toggle("ring-offset-4", isActive);
        swatch?.classList.toggle("ring-[#ff8a7a]", isActive);
        swatch?.classList.toggle("ring-offset-white", isActive);
      });
      if (customColorInput) {
        customColorInput.value = value || "#ff7448";
      }
    };

    const syncMoodButtons = () => {
      const selected = new Set(parseMoodKeywords(atmosphereInput?.value));
      moodButtons.forEach((button) => {
        const isActive = selected.has(button.dataset.moodChip);
        button.classList.toggle("ring-2", isActive);
        button.classList.toggle("ring-[#ff8a7a]", isActive);
        button.classList.toggle("ring-offset-2", isActive);
        button.classList.toggle("ring-offset-white", isActive);
        button.classList.toggle("brightness-95", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    };

    setActiveColor(state.onboarding.brandColor);
    syncMoodButtons();

    if (state.onboarding.logo?.name && logoName) {
      logoName.textContent = state.onboarding.logo.name;
    }

    brandNameInput?.addEventListener("input", (event) => {
      patchState({ onboarding: { brandName: event.target.value } });
    });

    atmosphereInput?.addEventListener("input", (event) => {
      patchState({ onboarding: { brandAtmosphere: event.target.value } });
      syncMoodButtons();
    });

    moodButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const keyword = button.dataset.moodChip;
        if (!keyword || !atmosphereInput) return;
        const keywords = parseMoodKeywords(atmosphereInput.value);
        const nextKeywords = keywords.includes(keyword)
          ? keywords.filter((item) => item !== keyword)
          : [...keywords, keyword];
        const nextValue = formatMoodKeywords(nextKeywords);
        atmosphereInput.value = nextValue;
        patchState({ onboarding: { brandAtmosphere: nextValue } });
        syncMoodButtons();
      });
    });

    colorButtons.forEach((button) => {
      button.dataset.value = button.dataset.brandColor;
      button.addEventListener("click", () => {
        const value = button.dataset.brandColor;
        setActiveColor(value);
        patchState({ onboarding: { brandColor: value } });
      });
    });

    customColorTrigger?.addEventListener("click", () => customColorInput?.click());
    customColorInput?.addEventListener("input", (event) => {
      const value = event.target.value;
      setActiveColor(value);
      patchState({ onboarding: { brandColor: value } });
    });

    logoTrigger?.addEventListener("click", () => logoInput?.click());
    logoInput?.addEventListener("change", async (event) => {
      const [file] = event.target.files || [];
      if (!file) return;
      const payload = await fileToPayload(file);
      patchState({ onboarding: { logo: payload } });
      if (logoName) {
        logoName.textContent = payload.name;
      }
    });

    selectOne("#step1-next")?.addEventListener("click", () => {
      navigate(PATHS.onboarding2);
    });
    selectOne("#step1-prev")?.addEventListener("click", () => {
      navigate(PATHS.welcome);
    });
    selectOne("#step1-back")?.addEventListener("click", () => {
      navigate(PATHS.welcome);
    });
  }

  function bindStep2() {
    const state = readState();
    const instagramInput = selectOne("#instagram-url-input");
    const imageInput = selectOne("#reference-image-input");
    const imageTrigger = selectOne("#reference-image-trigger");
    const imageStatus = selectOne("#reference-image-status");

    instagramInput.value = state.onboarding.instagramUrl || "";
    if (state.onboarding.referenceImages.length && imageStatus) {
      imageStatus.textContent = `${state.onboarding.referenceImages.length}장의 참고 이미지가 선택되어 있습니다.`;
    }

    instagramInput?.addEventListener("input", (event) => {
      patchState({ onboarding: { instagramUrl: event.target.value } });
    });

    imageTrigger?.addEventListener("click", () => imageInput?.click());
    imageInput?.addEventListener("change", async (event) => {
      const files = Array.from(event.target.files || []).slice(0, 4);
      if (!files.length) return;
      const payloads = await Promise.all(files.map(fileToPayload));
      patchState({ onboarding: { referenceImages: payloads } });
      if (imageStatus) {
        imageStatus.textContent = `${payloads.length}장의 참고 이미지를 저장했어요.`;
      }
    });

    selectOne("#step2-next")?.addEventListener("click", () => {
      navigate(PATHS.onboarding3);
    });
    selectOne("#step2-skip")?.addEventListener("click", () => {
      patchState({ onboarding: { instagramUrl: "", referenceImages: [] } });
      navigate(PATHS.onboarding3);
    });
    selectOne("#step2-back")?.addEventListener("click", () => {
      navigate(PATHS.onboarding1);
    });
  }

  function bindStep3() {
    const state = readState();
    const descriptionInput = selectOne("#brand-description");
    const submitButton = selectOne("#step3-submit");
    const prevButton = selectOne("#step3-prev");
    const statusNode = selectOne("#onboarding-status");
    const analysisPanel = selectOne("#onboarding-analysis-panel");
    const analysisTextNode = selectOne("#onboarding-analysis-text");
    const analysisBadgeNode = selectOne("#onboarding-analysis-badge");

    descriptionInput.value = state.onboarding.brandDescription || "";
    descriptionInput?.addEventListener("input", (event) => {
      patchState({
        onboarding: {
          brandDescription: event.target.value,
          analysisContent: "",
        },
      });
      analysisPanel?.classList.add("hidden");
      if (analysisTextNode) {
        analysisTextNode.textContent = "";
      }
      if (analysisBadgeNode) {
        analysisBadgeNode.textContent = "분석 대기";
      }
      if (submitButton) {
        submitButton.innerHTML = '분석하기 <span class="material-symbols-outlined" data-icon="arrow_forward">arrow_forward</span>';
      }
    });

    const applyAnalysisContent = (analysisContent, status = "created") => {
      const content = String(analysisContent || "").trim();
      if (!content) {
        analysisPanel?.classList.add("hidden");
        return;
      }

      if (analysisTextNode) {
        analysisTextNode.textContent = content;
      }
      if (analysisBadgeNode) {
        analysisBadgeNode.textContent = status === "existing" ? "기존 분석" : "AI 분석 완료";
      }
      analysisPanel?.classList.remove("hidden");
      if (submitButton) {
        submitButton.innerHTML = '다음 <span class="material-symbols-outlined" data-icon="arrow_forward">arrow_forward</span>';
      }
    };

    if (state.onboarding.analysisContent) {
      applyAnalysisContent(state.onboarding.analysisContent, "existing");
    }

    const submit = async (skipDescription) => {
      const currentState = readState();
      if (currentState.onboarding.analysisContent) {
        navigate(PATHS.onboarding4);
        return;
      }

      const nextState = patchState({
        onboarding: {
          brandDescription: skipDescription ? "" : descriptionInput.value,
        },
      });

      submitButton.disabled = true;
      if (prevButton) prevButton.disabled = true;
      setStatus(statusNode, "브랜드 가이드를 만드는 중입니다. 잠시만 기다려주세요.", "loading");

      try {
        const result = await api("/onboarding/complete", {
          method: "POST",
          body: {
            brand_name: nextState.onboarding.brandName,
            brand_color: nextState.onboarding.brandColor,
            brand_atmosphere: nextState.onboarding.brandAtmosphere,
            freetext: nextState.onboarding.brandDescription,
            instagram_url: nextState.onboarding.instagramUrl,
            logo: nextState.onboarding.logo,
            reference_images: nextState.onboarding.referenceImages,
          },
        });
        const analysisContent = result.brand?.content || "";
        patchState({
          onboarding: {
            analysisContent,
          },
        });
        applyAnalysisContent(analysisContent, result.status);
        setStatus(
          statusNode,
          result.status === "updated"
            ? "브랜드 정보를 새 입력값으로 업데이트했습니다. 아래 분석을 확인하고 다음 단계로 이동하세요."
            : result.status === "existing"
              ? "이미 저장된 브랜드가 있어 기존 분석을 그대로 보여드립니다. 확인 후 다음 단계로 이동하세요."
              : "브랜드 세팅이 완료되었습니다. 아래 분석을 확인하고 다음 단계로 이동하세요.",
          "success",
        );
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      } finally {
        submitButton.disabled = false;
        if (prevButton) prevButton.disabled = false;
      }
    };

    submitButton?.addEventListener("click", () => submit(false));
    prevButton?.addEventListener("click", () => {
      navigate(PATHS.onboarding2);
    });
    selectOne("#step3-back")?.addEventListener("click", () => {
      navigate(PATHS.onboarding2);
    });
  }

  async function bindWelcome() {
    const titleNode = selectOne("#welcome-title");
    const copyNode = selectOne("#welcome-copy");
    const startButton = selectOne("#welcome-start");
    const statusNode = selectOne("#welcome-status");

    try {
      const bootstrap = await api("/bootstrap");
      lastBootstrap = bootstrap;
      if (bootstrap.onboarding_completed) {
        navigate(PATHS.home);
        return;
      }
      if (titleNode) {
        titleNode.textContent = "사장님만의 홍보 도우미를 시작해볼까요?";
      }
      if (copyNode) {
        copyNode.textContent =
          "로고, 분위기, 참고 스타일을 차근차근 알려주시면 바로 메인 화면으로 이어집니다.";
      }
      startButton?.addEventListener("click", () => navigate(PATHS.onboarding1));
    } catch (error) {
      setStatus(statusNode, error.message, "error");
    }
  }

  async function bindStep4() {
    const statusNode = selectOne("#onboarding-instagram-status");
    const stateNode = selectOne("#onboarding-instagram-state");
    const copyNode = selectOne("#onboarding-instagram-copy");
    const noteNode = selectOne("#onboarding-instagram-note");
    const connectButton = selectOne("#onboarding-instagram-connect");
    const skipButton = selectOne("#onboarding-instagram-skip");
    const continueButton = selectOne("#onboarding-instagram-continue");
    const backButton = selectOne("#onboarding-instagram-back");
    const brandNameNode = selectOne("#onboarding-instagram-brand-name");
    const feedback = consumeInstagramFeedback();
    setInstagramPageGuide("#onboarding-page-guide", feedback);

    // CP20: 온보딩 — 다중 계정 선택 패널
    const igSelectPanel = selectOne("#onboarding-ig-select-panel");
    const igSelectEl = selectOne("#onboarding-ig-account-select");
    const igSelectConfirm = selectOne("#onboarding-ig-select-confirm");

    // CP20: 온보딩 — 수동 입력 패널
    const igManualPanel = selectOne("#onboarding-ig-manual-panel");
    const igManualInput = selectOne("#onboarding-ig-manual-input");
    const igManualConfirm = selectOne("#onboarding-ig-manual-confirm");

    if (feedback?.flag === "select_required" && igSelectPanel) {
      igSelectPanel.classList.remove("hidden");
      api("/instagram/candidates")
        .then((data) => {
          if (!igSelectEl) return;
          igSelectEl.innerHTML = "";
          (data.candidates || []).forEach((c) => {
            const opt = document.createElement("option");
            opt.value = c.instagram_account_id;
            opt.textContent = `@${c.instagram_username || c.instagram_account_id} (${c.facebook_page_name || ""})`;
            igSelectEl.appendChild(opt);
          });
        })
        .catch(() => {
          if (igSelectEl) igSelectEl.innerHTML = "<option>로드 실패</option>";
        });
    }

    if (feedback?.flag === "manual_required" && igManualPanel) {
      igManualPanel.classList.remove("hidden");
      api("/instagram/candidates")
        .then((data) => {
          if (igManualInput && data.env_account_id) {
            igManualInput.value = data.env_account_id;
          }
        })
        .catch(() => {});
    }

    igSelectConfirm?.addEventListener("click", async () => {
      const selectedId = igSelectEl?.value;
      if (!selectedId) {
        setStatus(statusNode, "계정을 선택해주세요.", "error");
        return;
      }
      try {
        setStatus(statusNode, "계정 연결 중…", "loading");
        await api("/instagram/select-account", { method: "POST", body: { instagram_account_id: selectedId } });
        igSelectPanel?.classList.add("hidden");
        await loadState();
        setStatus(statusNode, "인스타그램 계정 연결이 완료되었습니다.", "success");
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    igManualConfirm?.addEventListener("click", async () => {
      const igId = igManualInput?.value?.trim();
      if (!igId) {
        setStatus(statusNode, "Instagram 계정 ID를 입력해주세요.", "error");
        return;
      }
      try {
        setStatus(statusNode, "계정 확인 중…", "loading");
        await api("/instagram/manual-account", { method: "POST", body: { instagram_business_account_id: igId } });
        igManualPanel?.classList.add("hidden");
        await loadState();
        setStatus(statusNode, "인스타그램 계정 연결이 완료되었습니다.", "success");
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    const applyInstagramState = (summary, bootstrap) => {
      if (brandNameNode) {
        brandNameNode.textContent = bootstrap?.brand?.brand_name || "우리 가게";
      }
      if (stateNode) {
        stateNode.textContent = instagramStatusLabel(summary);
      }
      if (copyNode) {
        if (summary.connected) {
          copyNode.textContent =
            "계정 연결이 끝났어요. 이후 메인 화면과 업로드 준비 상태에 이 연결 정보를 바로 반영합니다.";
        } else if (summary.expired) {
          copyNode.textContent =
            "이전 연결이 만료되었습니다. 지금 다시 연결하거나, 나중에 설정 화면에서 이어서 연결할 수 있습니다.";
        } else if (summary.oauth_available) {
          copyNode.textContent =
            "지금 Meta 로그인으로 한 번만 연결해두면, 이후 피드와 스토리를 바로 업로드할 수 있습니다. 원하지 않으면 건너뛰어도 됩니다.";
        } else if (summary.connect_available) {
          copyNode.textContent =
            "이 화면의 연결 흐름은 준비되어 있습니다. 지금은 Meta 앱 설정이 없어 실제 로그인 창을 띄우지 못하지만, 설정만 붙으면 바로 연결을 시작할 수 있습니다.";
        } else {
          copyNode.textContent =
            "현재 환경에서는 계정 연결을 사용할 수 없습니다. 나중에 설정이 준비되면 설정 화면에서 Meta 로그인을 진행할 수 있습니다.";
        }
      }
      if (noteNode) {
        noteNode.textContent = summary.connected
          ? "설정 화면에서 언제든 재연결하거나 해제할 수 있습니다."
          : "이 단계는 선택입니다. 지금 건너뛰어도 메인 화면에서 홍보물 만들기를 바로 시작할 수 있습니다.";
      }

      if (connectButton) {
        connectButton.classList.toggle(
          "hidden",
          !bootstrap?.onboarding_completed || !summary.connect_available || summary.connected,
        );
        connectButton.textContent = summary.expired ? "Meta로 다시 연결하기" : "Meta로 계속하기";
      }
    };

    const loadState = async () => {
      const [bootstrap, instagram] = await Promise.all([
        api("/bootstrap"),
        api("/instagram/status"),
      ]);
      lastBootstrap = {
        ...bootstrap,
        instagram,
        instagram_ready: instagram.upload_ready,
      };
      if (!bootstrap.onboarding_completed) {
        navigate(PATHS.welcome);
        return null;
      }
      applyInstagramState(instagram, bootstrap);
      return { bootstrap, instagram };
    };

    connectButton?.addEventListener("click", async () => {
      try {
        setStatus(statusNode, "Meta 인증 페이지로 이동하는 중입니다.", "loading");
        const response = await api("/instagram/connect-url", {
          method: "POST",
          body: { source: "onboarding" },
        });
        if (response.mode === "oauth" && response.url) {
          window.location.assign(response.url);
          return;
        }
        setStatus(
          statusNode,
          response.message || "Meta 로그인 설정이 아직 연결되지 않아 실제 연결 화면을 열 수 없습니다.",
          "neutral",
        );
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    skipButton?.addEventListener("click", () => navigate(PATHS.home));
    continueButton?.addEventListener("click", () => navigate(PATHS.home));
    backButton?.addEventListener("click", () => navigate(PATHS.onboarding3));

    try {
      await loadState();
      if (feedback) {
        setStatus(statusNode, feedback.message, feedback.tone);
        if (feedback.flag === "page_required" && copyNode) {
          copyNode.textContent =
            "Meta 로그인은 완료됐지만 Facebook Page 연결이 확인되지 않았습니다. 아래 안내대로 Page를 연결한 뒤 다시 시도해 주세요.";
        }
      }
    } catch (error) {
      setStatus(statusNode, error.message, "error");
    }
  }

  function renderBrandSummary(brand, counts) {
    if (!brand) return;
    const name = selectOne("#brand-summary-name");
    const chips = selectOne("#brand-summary-tags");
    const colorDot = selectOne("#brand-summary-color-dot");
    const colorLabel = selectOne("#brand-summary-color-label");
    const logoStatus = selectOne("#brand-summary-logo-status");
    const statusHint = selectOne("#reference-pool-hint");

    if (name) {
      name.textContent = brand.brand_name || "우리 브랜드";
    }
    if (chips) {
      chips.innerHTML = "";
      const chipValues = [brand.brand_atmosphere, "브랜드 저장 완료"].filter(Boolean);
      chipValues.forEach((value, index) => {
        const span = document.createElement("span");
        span.className =
          index === 0
            ? "px-3 py-1 bg-[rgba(255,116,72,0.15)] text-[#d95c39] text-[10px] font-bold rounded-full tracking-wider"
            : "px-3 py-1 bg-[rgba(255,179,71,0.14)] text-on-surface-variant text-[10px] font-bold rounded-full tracking-wider";
        span.textContent = index === 0 ? `#${value}` : value;
        chips.appendChild(span);
      });
    }
    if (colorDot && brand.brand_color) {
      colorDot.style.backgroundColor = brand.brand_color;
    }
    if (colorLabel) {
      colorLabel.textContent = brand.brand_color
        ? `대표 컬러: ${brand.brand_color}`
        : "대표 컬러 미설정";
    }
    if (logoStatus) {
      logoStatus.textContent = brand.brand_logo_url ? "로고 등록 완료" : "로고 미등록";
    }
    if (statusHint) {
      statusHint.textContent =
        counts.published_reference_count > 0
          ? `지난 게시물 ${counts.published_reference_count}건이 있어요. 직접 업로드도 함께 쓸 수 있습니다.`
          : "직접 업로드한 이미지가 우선 참고 이미지로 사용됩니다.";
    }
  }

  function renderGenerateResult(result) {
    const wrap = selectOne("#create-results");
    const summaryBlock = selectOne("#result-summary-block");
    const textBlock = selectOne("#result-text-block");
    const imageBlock = selectOne("#result-image-block");
    const previewBlock = selectOne("#result-preview-block");
    const captionBlock = selectOne("#result-caption-block");
    const storyBlock = selectOne("#result-story-block");
    const actionRow = selectOne("#result-actions");
    const storyChooser = selectOne("#story-copy-chooser");
    const captionButton = selectOne("#create-caption-button");
    const storyButton = selectOne("#create-story-button");
    const saveImageLink = selectOne("#create-save-image-link");
    const uploadFeedButton = selectOne("#create-upload-feed-button");
    const uploadStoryButton = selectOne("#create-upload-story-button");
    const uploadNote = selectOne("#result-upload-note");
    const canCaption = Boolean(result.text_result?.ad_copies?.length);
    const canStory = Boolean(
      result.image_data_url && (result.text_result?.story_copies || []).length,
    );
    const state = readState();
    const brand = lastBootstrap?.brand;
    const instagram = getInstagramSummary(lastBootstrap);
    const brandName = brand?.brand_name || state.onboarding.brandName || "우리 가게";
    const handle = parseInstagramHandle(state.onboarding.instagramUrl, brandName);
    const previewCaption =
      result.text_result?.ad_copies?.[0] ||
      result.text_result?.promo_sentences?.[0] ||
      `${state.create.productName} 홍보 문구`;
    const preferenceUploadEnabled = state.preferences.uploadPlaceholderEnabled;

    wrap?.classList.remove("hidden");
    summaryBlock?.classList.add("hidden");
    textBlock?.classList.add("hidden");
    imageBlock?.classList.add("hidden");
    previewBlock?.classList.add("hidden");
    captionBlock?.classList.add("hidden");
    storyBlock?.classList.add("hidden");
    actionRow?.classList.add("hidden");
    storyChooser?.classList.add("hidden");
    uploadNote?.classList.add("hidden");

    if (captionBlock) captionBlock.innerHTML = "";
    if (storyBlock) storyBlock.innerHTML = "";

    if (summaryBlock) {
      summaryBlock.innerHTML = `
        <div class="result-card">
          <div class="tag-list" style="margin-bottom:0.8rem;">
            <span class="mini-tag">${escapeHtml(state.create.goal)}</span>
            <span class="mini-tag">${escapeHtml(
              state.create.generationType === "both"
                ? "글 + 이미지"
                : state.create.generationType === "image"
                  ? "이미지"
                  : "글",
            )}</span>
            <span class="mini-tag">${escapeHtml(state.create.tone)}</span>
            <span class="mini-tag">${escapeHtml(state.create.style)}</span>
          </div>
          <h3 class="result-card__title">광고 세트가 완성됐어요</h3>
          <p class="panel-copy">인스타그램 프리뷰와 저장 버튼까지 한 번에 확인한 뒤, 캡션·스토리까지 이어서 만들 수 있습니다.</p>
        </div>
      `;
      summaryBlock.classList.remove("hidden");
    }

    if (result.image_data_url && imageBlock) {
      imageBlock.innerHTML = `
        <div class="result-card">
          <h3 class="result-card__title">생성된 이미지</h3>
          <img class="result-media" src="${result.image_data_url}" alt="생성된 홍보 이미지" />
        </div>
      `;
      imageBlock.classList.remove("hidden");
      if (saveImageLink) {
        saveImageLink.href = result.image_data_url;
        saveImageLink.classList.remove("hidden");
      }
    } else if (saveImageLink) {
      saveImageLink.classList.add("hidden");
    }

    if (previewBlock) {
      const previewMedia = result.image_data_url
        ? `<img class="ig-image" src="${result.image_data_url}" alt="인스타그램 피드 미리보기 이미지" />`
        : `<div class="ig-image"></div>`;
      previewBlock.innerHTML = `
        <div class="ig-card">
          <div class="ig-header">
            <div class="ig-avatar"></div>
            <div>
              <p class="ig-name">${escapeHtml(handle)}</p>
              <p class="ig-sub">${escapeHtml(brandName)} · Sponsored</p>
            </div>
          </div>
          ${previewMedia}
          <div class="ig-actions">♡ 💬 ↗</div>
          <div class="ig-caption">
            <b>${escapeHtml(handle)}</b>${escapeHtml(previewCaption)}
          </div>
        </div>
      `;
      previewBlock.classList.remove("hidden");
    }

    if (result.text_result && textBlock) {
      const adCopies = (result.text_result.ad_copies || [])
        .map((copy) => `<div class="copy-line">${escapeHtml(copy)}</div>`)
        .join("");
      const promoSentences = (result.text_result.promo_sentences || [])
        .map((copy) => `<div class="copy-line">${escapeHtml(copy)}</div>`)
        .join("");

      textBlock.innerHTML = `
        <div class="result-card">
          <h3 class="result-card__title">광고 문구</h3>
          <div class="copy-stack" style="margin-bottom:0.9rem;">
            ${adCopies || `<div class="copy-line">생성된 짧은 카피가 아직 없습니다.</div>`}
          </div>
          <div class="copy-stack">
            ${promoSentences || `<div class="copy-line">상세 소개 문장은 이번 생성에서 생략되었습니다.</div>`}
          </div>
        </div>
      `;
      textBlock.classList.remove("hidden");
    }

    if (actionRow) {
      actionRow.classList.remove("hidden");
      captionButton?.classList.toggle("hidden", !canCaption);
      storyButton?.classList.toggle("hidden", !canStory);
      if (captionButton) captionButton.disabled = !canCaption;
      if (storyButton) storyButton.disabled = !canStory;
      applyUploadButtonState();
    }

    if (preferenceUploadEnabled && uploadNote) {
      uploadNote.innerHTML = buildUploadPlaceholder(instagram, "feed").html;
      uploadNote.className = "upload-note";
      uploadNote.classList.remove("hidden");
    }

    const storyCopies = result.text_result?.story_copies || [];
    if (canStory && storyCopies.length && storyChooser) {
      storyChooser.innerHTML = `
        <div class="result-card">
          <h3 class="result-card__title">스토리 문구 선택</h3>
          <div class="copy-stack">
            ${storyCopies
              .map(
                (copy, index) => `
                  <label class="story-option">
                    <input ${index === 0 ? "checked" : ""} type="radio" name="story-copy" value="${escapeHtml(copy)}" />
                    <span>${escapeHtml(copy)}</span>
                  </label>`,
              )
              .join("")}
          </div>
        </div>
      `;
      storyChooser.classList.remove("hidden");
    }
  }

  function renderHome(bootstrap) {
    const state = readState();
    const brand = bootstrap?.brand;
    const heroEyebrow = selectOne("#home-hero-eyebrow");
    const heroTitle = selectOne("#home-hero-title");
    const heroCopy = selectOne("#home-hero-copy");
    const primaryCta = selectOne("#home-primary-cta");
    const secondaryCta = selectOne("#home-secondary-cta");
    const metricHistory = selectOne("#home-metric-history");
    const metricProducts = selectOne("#home-metric-products");
    const metricReferences = selectOne("#home-metric-references");
    const statusList = selectOne("#home-status-list");
    const guideCopy = selectOne("#home-guide-copy");
    const instagram = getInstagramSummary(bootstrap);

    const recentCount = state.history.length;
    if (metricHistory) metricHistory.textContent = `${recentCount}건`;
    if (metricProducts) metricProducts.textContent = `${bootstrap?.product_count || 0}개`;
    if (metricReferences) {
      metricReferences.textContent = `${bootstrap?.published_reference_count || 0}건`;
    }

    if (bootstrap?.onboarding_completed) {
      if (heroEyebrow) heroEyebrow.textContent = "Today with Brewgram";
      if (heroTitle) {
        heroTitle.textContent = `${brand?.brand_name || "우리 가게"}용 새 홍보물을 만들어볼까요?`;
      }
      if (heroCopy) {
        heroCopy.textContent =
          bootstrap?.image_backend_kind === "remote_worker"
            ? "실제 워커와 연결된 이미지 생성 경로를 사용 중입니다. 결과 화면에서 업로드 UI까지 함께 확인해보세요."
            : "상품 하나만 넣으면 문구와 이미지, 피드 프리뷰까지 한 번에 만들어집니다.";
      }
      if (primaryCta) {
        primaryCta.href = PATHS.create;
        primaryCta.innerHTML =
          '<span class="material-symbols-outlined">auto_awesome</span>새 홍보 만들기';
      }
      if (secondaryCta) {
        secondaryCta.href = PATHS.archive;
        secondaryCta.innerHTML =
          '<span class="material-symbols-outlined">inventory_2</span>최근 결과 보기';
      }
    }

    if (statusList) {
      const statuses = [
        brand?.brand_atmosphere ? `#${brand.brand_atmosphere}` : "브랜드 세팅 완료",
        bootstrap?.image_backend_kind === "remote_worker"
          ? "실제 이미지 생성 연결됨"
          : bootstrap?.image_backend_kind === "mock"
            ? "미리보기 생성 모드"
            : "이미지 생성 준비 완료",
      ].filter(Boolean);
      statusList.innerHTML = statuses
        .map((value) => `<span class="status-pill">${escapeHtml(value)}</span>`)
        .join("");
    }

    if (guideCopy) {
      guideCopy.textContent = instagramGuideCopy(instagram);
    }

    renderHistoryList(selectOne("#home-recent-list"), state.history.slice(0, 3), {
      title: "아직 최근 홍보물이 없어요",
      copy: "새 홍보물을 만들면 홈에서 최근 결과를 바로 다시 볼 수 있습니다.",
      href: PATHS.create,
      label: "첫 홍보물 만들기",
    });
  }

  async function bindHome() {
    const statusNode = selectOne("#home-status");
    const state = readState();
    renderHistoryList(selectOne("#home-recent-list"), state.history.slice(0, 3), {
      title: "아직 최근 홍보물이 없어요",
      copy: "새 홍보물을 만들면 홈에서 최근 결과를 바로 다시 볼 수 있습니다.",
      href: PATHS.create,
      label: "첫 홍보물 만들기",
    });

    try {
      const bootstrap = await api("/bootstrap");
      if (!bootstrap.onboarding_completed) {
        navigate(PATHS.welcome);
        return;
      }
      lastBootstrap = bootstrap;
      renderHome(bootstrap);
    } catch (error) {
      setStatus(statusNode, error.message, "error");
    }
  }

  async function bindArchive() {
    try {
      const bootstrap = await api("/bootstrap");
      if (!bootstrap.onboarding_completed) {
        navigate(PATHS.welcome);
        return;
      }
    } catch (_) {
      navigate(PATHS.welcome);
      return;
    }
    const state = readState();
    const title = selectOne("#archive-title");
    const list = selectOne("#archive-list");
    if (title) {
      title.textContent = `보관함 · ${state.history.length}개`;
    }
    renderHistoryList(list, state.history, {
      title: "보관함이 비어 있어요",
      copy: "생성 결과는 세션 기준으로 여기에 쌓입니다. 먼저 하나 만들어보세요.",
      href: PATHS.create,
      label: "만들기로 이동",
    });
  }

  async function bindSettings() {
    const state = readState();
    const toneSelect = selectOne("#settings-default-tone");
    const styleSelect = selectOne("#settings-default-style");
    const notifyToggle = selectOne("#settings-notify-toggle");
    const uploadToggle = selectOne("#settings-upload-toggle");
    const statusNode = selectOne("#settings-status");
    const instagramCopyNode = selectOne("#settings-instagram-copy");
    const instagramNode = selectOne("#settings-instagram-status");
    const instagramNoteNode = selectOne("#settings-instagram-note");
    const instagramConnectButton = selectOne("#settings-instagram-connect");
    const instagramReconnectButton = selectOne("#settings-instagram-reconnect");
    const instagramDisconnectButton = selectOne("#settings-instagram-disconnect");
    const installStatusNode = selectOne("#settings-install-status");
    const installCopyNode = selectOne("#settings-install-copy");
    const installButton = selectOne("#settings-install-button");
    const installHintNode = selectOne("#settings-install-hint");

    if (toneSelect) toneSelect.value = state.preferences.defaultTone;
    if (styleSelect) styleSelect.value = state.preferences.defaultStyle;
    applyToggleState(notifyToggle, state.preferences.notificationsEnabled);
    applyToggleState(uploadToggle, state.preferences.uploadPlaceholderEnabled);

    toneSelect?.addEventListener("change", (event) => {
      patchState({
        preferences: { defaultTone: event.target.value },
        create: { tone: event.target.value },
      });
      setStatus(statusNode, "기본 톤을 저장했습니다.", "success");
    });

    styleSelect?.addEventListener("change", (event) => {
      patchState({
        preferences: { defaultStyle: event.target.value },
        create: { style: event.target.value },
      });
      setStatus(statusNode, "기본 이미지 스타일을 저장했습니다.", "success");
    });

    notifyToggle?.addEventListener("click", () => {
      const nextValue = !readState().preferences.notificationsEnabled;
      patchState({ preferences: { notificationsEnabled: nextValue } });
      applyToggleState(notifyToggle, nextValue);
      setStatus(statusNode, "알림 표시 상태를 저장했습니다.", "success");
    });

    uploadToggle?.addEventListener("click", () => {
      const nextValue = !readState().preferences.uploadPlaceholderEnabled;
      patchState({ preferences: { uploadPlaceholderEnabled: nextValue } });
      applyToggleState(uploadToggle, nextValue);
      setStatus(statusNode, "업로드 안내 표시 상태를 저장했습니다.", "success");
    });

    const feedback = consumeInstagramFeedback();
    setInstagramPageGuide("#settings-page-guide", feedback);

    // CP20: 다중 계정 선택 패널
    const igSelectPanel = selectOne("#settings-ig-select-panel");
    const igSelectEl = selectOne("#settings-ig-account-select");
    const igSelectConfirm = selectOne("#settings-ig-select-confirm");

    // CP20: 수동 입력 패널
    const igManualPanel = selectOne("#settings-ig-manual-panel");
    const igManualInput = selectOne("#settings-ig-manual-input");
    const igManualConfirm = selectOne("#settings-ig-manual-confirm");

    if (feedback?.flag === "select_required" && igSelectPanel) {
      igSelectPanel.classList.remove("hidden");
      // 후보 목록 로드
      api("/instagram/candidates")
        .then((data) => {
          if (!igSelectEl) return;
          igSelectEl.innerHTML = "";
          (data.candidates || []).forEach((c) => {
            const opt = document.createElement("option");
            opt.value = c.instagram_account_id;
            opt.textContent = `@${c.instagram_username || c.instagram_account_id} (${c.facebook_page_name || ""})`;
            igSelectEl.appendChild(opt);
          });
        })
        .catch(() => {
          if (igSelectEl) igSelectEl.innerHTML = "<option>로드 실패</option>";
        });
    }

    if (feedback?.flag === "manual_required" && igManualPanel) {
      igManualPanel.classList.remove("hidden");
      // .env INSTAGRAM_ACCOUNT_ID 를 기본값으로 채움 (Streamlit 동등)
      api("/instagram/candidates")
        .then((data) => {
          if (igManualInput && data.env_account_id) {
            igManualInput.value = data.env_account_id;
          }
        })
        .catch(() => {});
    }

    igSelectConfirm?.addEventListener("click", async () => {
      const selectedId = igSelectEl?.value;
      if (!selectedId) {
        setStatus(statusNode, "계정을 선택해주세요.", "error");
        return;
      }
      try {
        setStatus(statusNode, "계정 연결 중…", "loading");
        await api("/instagram/select-account", {
          method: "POST",
          body: { instagram_account_id: selectedId },
        });
        igSelectPanel?.classList.add("hidden");
        await loadSettingsStatus();
        setStatus(statusNode, "인스타그램 계정 연결이 완료되었습니다.", "success");
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    igManualConfirm?.addEventListener("click", async () => {
      const igId = igManualInput?.value?.trim();
      if (!igId) {
        setStatus(statusNode, "Instagram 계정 ID를 입력해주세요.", "error");
        return;
      }
      try {
        setStatus(statusNode, "계정 확인 중…", "loading");
        await api("/instagram/manual-account", {
          method: "POST",
          body: { instagram_business_account_id: igId },
        });
        igManualPanel?.classList.add("hidden");
        await loadSettingsStatus();
        setStatus(statusNode, "인스타그램 계정 연결이 완료되었습니다.", "success");
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    const applyPwaInstallState = () => {
      const installState = getPwaInstallState();
      if (!installStatusNode || !installCopyNode || !installButton || !installHintNode) {
        return;
      }

      if (installState === "installed") {
        installStatusNode.textContent = "설치됨";
        installCopyNode.textContent = "홈 화면 아이콘으로 바로 열 수 있습니다. 주소창 없이 앱처럼 실행됩니다.";
        installHintNode.textContent = "이미 홈 화면에 추가되어 있습니다.";
        installButton.textContent = "이미 설치됨";
        installButton.disabled = true;
        return;
      }

      installButton.disabled = false;

      if (installState === "available") {
        installStatusNode.textContent = "설치 가능";
        installCopyNode.textContent = "이 기기에서는 설치 프롬프트를 바로 열 수 있습니다.";
        installHintNode.textContent = "버튼을 누르면 홈 화면 설치 안내가 바로 열립니다.";
        installButton.textContent = "홈 화면에 설치하기";
        return;
      }

      if (installState === "ios_manual") {
        installStatusNode.textContent = "수동 추가";
        installCopyNode.textContent = "iPhone/iPad는 Safari 공유 메뉴에서 홈 화면에 추가해야 합니다.";
        installHintNode.textContent = "Safari 공유 버튼 -> 홈 화면에 추가 순서로 진행하세요.";
        installButton.textContent = "설치 방법 보기";
        return;
      }

      if (installState === "manual") {
        installStatusNode.textContent = "브라우저 메뉴";
        installCopyNode.textContent = "브라우저 메뉴의 설치 또는 홈 화면에 추가 기능을 사용하세요.";
        installHintNode.textContent = "Android Chrome, Samsung Internet 등에서 메뉴의 설치 항목을 확인하세요.";
        installButton.textContent = "설치 안내 보기";
        return;
      }

      installStatusNode.textContent = "설치 제한";
      installCopyNode.textContent = "홈 화면 설치는 HTTPS 환경과 지원 브라우저가 필요합니다.";
      installHintNode.textContent = "운영 도메인에서 HTTPS를 붙인 뒤 다시 확인하면 설치 조건이 충족됩니다.";
      installButton.textContent = "설치 조건 보기";
    };

    applyPwaInstallState();
    window.addEventListener("brewgram:pwa-install-state", applyPwaInstallState);

    const applyInstagramSettings = (instagram, bootstrap) => {
      const onboardingCompleted = Boolean(bootstrap?.onboarding_completed);
      if (instagramNode) {
        instagramNode.textContent = instagramStatusLabel(instagram);
      }
      if (instagramCopyNode) {
        instagramCopyNode.textContent = instagramStatusCopy(instagram, onboardingCompleted);
      }
      if (instagramNoteNode) {
        instagramNoteNode.textContent = instagramSettingsNote(instagram, onboardingCompleted);
      }

      const canConnect = onboardingCompleted && instagram.connect_available && !instagram.connected && !instagram.expired;
      const canReconnect = onboardingCompleted && instagram.connect_available && (instagram.connected || instagram.expired);
      const canDisconnect = onboardingCompleted && (instagram.connected || instagram.expired);

      instagramConnectButton?.classList.toggle("hidden", !canConnect);
      instagramReconnectButton?.classList.toggle("hidden", !canReconnect);
      instagramDisconnectButton?.classList.toggle("hidden", !canDisconnect);
      if (instagramConnectButton) {
        instagramConnectButton.textContent = "Meta로 연결하기";
      }
      if (instagramReconnectButton) {
        instagramReconnectButton.textContent = "Meta로 다시 연결하기";
      }
    };

    const loadSettingsStatus = async () => {
      const [bootstrap, instagram] = await Promise.all([
        api("/bootstrap"),
        api("/instagram/status"),
      ]);
      if (!bootstrap.onboarding_completed) {
        navigate(PATHS.welcome);
        return null;
      }
      lastBootstrap = {
        ...bootstrap,
        instagram,
        instagram_ready: instagram.upload_ready,
      };
      const brand = bootstrap.brand;
      const brandNameNode = selectOne("#settings-brand-name");
      const brandSubNode = selectOne("#settings-brand-sub");
      const apiNode = selectOne("#settings-api-status");
      const backendNode = selectOne("#settings-image-backend");

      if (brandNameNode) {
        brandNameNode.textContent = brand?.brand_name || "미설정";
      }
      if (brandSubNode) {
        brandSubNode.textContent = brand
          ? `${brand.brand_color || "대표 컬러 미설정"} · ${brand.brand_atmosphere || "분위기 미설정"}`
          : "온보딩이 아직 완료되지 않았습니다.";
      }
      if (apiNode) {
        apiNode.textContent = bootstrap.api_ready ? "사용 가능" : "확인 필요";
      }
      if (backendNode) {
        backendNode.textContent = bootstrap.image_backend_kind || "미확인";
      }
      applyInstagramSettings(instagram, bootstrap);
      return { bootstrap, instagram };
    };

    instagramConnectButton?.addEventListener("click", async () => {
      try {
        setStatus(statusNode, "Meta 인증 페이지로 이동하는 중입니다.", "loading");
        const response = await api("/instagram/connect-url", {
          method: "POST",
          body: { source: "settings" },
        });
        if (response.mode === "oauth" && response.url) {
          window.location.assign(response.url);
          return;
        }
        setStatus(
          statusNode,
          response.message || "Meta 로그인 설정이 아직 연결되지 않아 실제 연결 화면을 열 수 없습니다.",
          "neutral",
        );
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    instagramReconnectButton?.addEventListener("click", async () => {
      try {
        setStatus(statusNode, "Meta 인증 페이지로 다시 이동합니다.", "loading");
        const response = await api("/instagram/connect-url", {
          method: "POST",
          body: { source: "settings" },
        });
        if (response.mode === "oauth" && response.url) {
          window.location.assign(response.url);
          return;
        }
        setStatus(
          statusNode,
          response.message || "Meta 로그인 설정이 아직 연결되지 않아 실제 연결 화면을 열 수 없습니다.",
          "neutral",
        );
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    instagramDisconnectButton?.addEventListener("click", async () => {
      try {
        await api("/instagram/disconnect", { method: "POST" });
        await loadSettingsStatus();
        setStatus(statusNode, "인스타그램 계정 연결을 해제했습니다.", "success");
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      }
    });

    installButton?.addEventListener("click", async () => {
      const installState = getPwaInstallState();
      if (installState === "installed") {
        setStatus(statusNode, "이미 홈 화면에 설치되어 있습니다.", "success");
        return;
      }

      if (deferredInstallPrompt) {
        deferredInstallPrompt.prompt();
        const choice = await deferredInstallPrompt.userChoice.catch(() => null);
        deferredInstallPrompt = null;
        notifyPwaInstallStatusChange();
        if (choice?.outcome === "accepted") {
          setStatus(statusNode, "홈 화면 설치를 시작했습니다. 설치가 끝나면 앱 목록에서 Brewgram을 확인하세요.", "success");
          return;
        }
        setStatus(statusNode, "설치를 취소했습니다. 나중에 다시 시도할 수 있습니다.", "neutral");
        return;
      }

      if (isIOSDevice()) {
        setStatus(statusNode, "Safari 공유 메뉴에서 '홈 화면에 추가'를 선택해주세요.", "neutral");
        return;
      }

      if (window.isSecureContext) {
        setStatus(statusNode, "브라우저 메뉴에서 '설치' 또는 '홈 화면에 추가'를 선택해주세요.", "neutral");
        return;
      }

      setStatus(statusNode, "현재 환경은 설치 조건을 충족하지 않습니다. 운영 도메인에 HTTPS를 붙인 뒤 다시 시도해주세요.", "neutral");
    });

    try {
      const payload = await loadSettingsStatus();
      if (!payload) return;
      if (feedback) {
        setStatus(statusNode, feedback.message, feedback.tone);
        if (feedback.flag === "page_required" && instagramCopyNode) {
          instagramCopyNode.textContent =
            "Meta 로그인은 완료됐지만 업로드할 Instagram professional account와 연결된 Facebook Page가 아직 없습니다.";
        }
      }
    } catch (error) {
      setStatus(statusNode, error.message, "error");
    }
  }

  async function bindCreate() {
    const state = readState();
    const bootstrapStatus = selectOne("#create-status");
    const productNameInput = selectOne("#create-product-name");
    const descriptionInput = selectOne("#create-product-description");
    const toneSelect = selectOne("#create-tone-select");
    const styleSelect = selectOne("#create-style-select");
    const customGoalInput = selectOne("#create-goal-custom");
    const productImagePanel = selectOne("#create-product-image-panel");
    const productImageTrigger = selectOne("#create-product-image-trigger");
    const productImageInput = selectOne("#create-product-image-input");
    const productImageStatus = selectOne("#create-product-image-status");
    const referenceUrlInput = selectOne("#create-reference-url");
    const referenceTrigger = selectOne("#create-reference-trigger");
    const referenceInput = selectOne("#create-reference-input");
    const referenceStatus = selectOne("#create-reference-status");
    const submitButton = selectOne("#create-submit");
    const captionButton = selectOne("#create-caption-button");
    const storyButton = selectOne("#create-story-button");
    const regenerateButton = selectOne("#create-regenerate-button");
    const uploadFeedButton = selectOne("#create-upload-feed-button");
    const uploadStoryButton = selectOne("#create-upload-story-button");
    const uploadNote = selectOne("#result-upload-note");
    const captionBlock = selectOne("#result-caption-block");
    const storyBlock = selectOne("#result-story-block");

    try {
      const bootstrap = await api("/bootstrap");
      if (!bootstrap.onboarding_completed) {
        navigate(PATHS.welcome);
        return;
      }
      lastBootstrap = bootstrap;
      renderBrandSummary(bootstrap.brand, bootstrap);
    } catch (error) {
      setStatus(bootstrapStatus, error.message, "error");
    }

    const effectiveTone = state.create.tone || state.preferences.defaultTone || "감성";
    const effectiveStyle = state.create.style || state.preferences.defaultStyle || "감성";
    const customGoalValue = PRESET_GOALS.includes(state.create.goal) ? "" : state.create.goal || "";

    productNameInput.value = state.create.productName || "";
    descriptionInput.value = state.create.productDescription || "";
    toneSelect.value = effectiveTone;
    styleSelect.value = effectiveStyle;
    if (customGoalInput) customGoalInput.value = customGoalValue;
    referenceUrlInput.value = state.create.referenceUrl || "";

    if (state.create.productImage && productImageStatus) {
      productImageStatus.textContent = `${state.create.productImage.name} 파일이 상품 사진으로 연결되어 있어요.`;
    }

    if (state.create.referenceImage && referenceStatus) {
      referenceStatus.textContent = `${state.create.referenceImage.name} 파일이 연결되어 있어요.`;
    }

    const goalButtons = selectAll("[data-goal-choice]");
    goalButtons.forEach((button) => {
      button.dataset.value = button.dataset.goalChoice;
    });
    const generationButtons = selectAll("[data-generation-type]");
    generationButtons.forEach((button) => {
      button.dataset.value = button.dataset.generationType;
    });

    const applyGoalStyles = (goal) =>
      highlightChoice(goalButtons, goal, {
        active: "bg-tertiary-container",
        inactive: "bg-surface-container-highest",
        activeText: "text-on-tertiary-container",
        inactiveText: "text-on-surface-variant",
      });
    const applyGenerationStyles = (generationType) =>
      highlightChoice(generationButtons, generationType, {
        active: "border-primary/30 bg-primary-container/15",
        inactive: "border-outline-variant/20 bg-surface-container-lowest",
        activeText: "text-primary",
        inactiveText: "text-on-surface-variant",
      });

    const newProductToggle = selectOne("#create-new-product-toggle");
    const existingProductPanel = selectOne("#create-existing-product-panel");
    const existingProductSelect = selectOne("#create-existing-product-select");
    const existingProductThumbWrap = selectOne("#create-existing-product-thumb-wrap");
    const existingProductThumb = selectOne("#create-existing-product-thumb");

    const syncProductImageUi = (isNewProduct) => {
      productImagePanel?.classList.toggle("hidden", !isNewProduct);
      existingProductPanel?.classList.toggle("hidden", isNewProduct);
      if (!productImageStatus) return;
      if (!isNewProduct) {
        productImageStatus.textContent = "";
        return;
      }
      if (readState().create.productImage?.name) {
        productImageStatus.textContent = `${readState().create.productImage.name} 파일이 상품 사진으로 준비되었습니다.`;
        return;
      }
      productImageStatus.textContent = "신상품 사진을 업로드해주세요.";
    };

    // 신상품 토글 OFF → "신제품 출시" goal 버튼 숨김 + 선택 시 자동 리셋
    const syncGoalAvailability = (isNewProduct) => {
      goalButtons.forEach((btn) => {
        if (btn.dataset.goalChoice === NEW_PRODUCT_GOAL_PREFIX) {
          btn.classList.toggle("hidden", !isNewProduct);
          btn.disabled = false;
          btn.classList.remove("opacity-30", "cursor-not-allowed");
        }
      });
      // 토글 OFF인데 현재 goal이 "신제품 출시"면 첫 번째 허용 goal로 리셋
      if (!isNewProduct && readState().create.goal === NEW_PRODUCT_GOAL_PREFIX) {
        const fallback = PRESET_GOALS.find((g) => g !== NEW_PRODUCT_GOAL_PREFIX) || PRESET_GOALS[1];
        patchState({ create: { goal: fallback } });
        applyGoalStyles(fallback);
      }
    };

    // 기존 상품 목록 fetch → 드롭다운 채우기
    try {
      const productsData = await api("/products");
      if (productsData.products && existingProductSelect) {
        productsData.products.forEach((pg) => {
          const opt = document.createElement("option");
          opt.value = pg.product_name;
          opt.textContent = `${pg.product_name} (${pg.generation_count}회)`;
          opt.dataset.imageUrl = pg.product_image_url || "";
          opt.dataset.description = pg.product_description || "";
          existingProductSelect.appendChild(opt);
        });
      }
    } catch (_e) {
      // 상품 목록 로드 실패 시 무시 (드롭다운 비어있게 됨)
    }

    // 토글 초기값 적용
    if (newProductToggle) {
      newProductToggle.checked = state.create.isNewProduct;
    }

    applyGoalStyles(state.create.goal);
    applyGenerationStyles(state.create.generationType);
    syncProductImageUi(state.create.isNewProduct);
    syncGoalAvailability(state.create.isNewProduct);

    goalButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (button.disabled) return;
        const value = button.dataset.goalChoice;
        patchState({ create: { goal: value } });
        applyGoalStyles(value);
        if (customGoalInput) {
          customGoalInput.value = "";
        }
      });
    });

    // 신상품 토글 리스너
    newProductToggle?.addEventListener("change", () => {
      const checked = newProductToggle.checked;
      patchState({ create: { isNewProduct: checked, selectedProductName: "", selectedProductImageUrl: null } });
      syncProductImageUi(checked);
      syncGoalAvailability(checked);
    });

    generationButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.generationType;
        patchState({ create: { generationType: value } });
        applyGenerationStyles(value);
      });
    });

    productNameInput?.addEventListener("input", (event) => {
      patchState({ create: { productName: event.target.value } });
    });
    descriptionInput?.addEventListener("input", (event) => {
      patchState({ create: { productDescription: event.target.value } });
    });
    customGoalInput?.addEventListener("input", (event) => {
      const fallbackGoal = readState().create.isNewProduct
        ? NEW_PRODUCT_GOAL_PREFIX
        : PRESET_GOALS.find((g) => g !== NEW_PRODUCT_GOAL_PREFIX) || PRESET_GOALS[1];
      const nextGoal = event.target.value.trim() || fallbackGoal;
      patchState({ create: { goal: nextGoal } });
      applyGoalStyles(nextGoal);
    });
    toneSelect?.addEventListener("change", (event) => {
      patchState({ create: { tone: event.target.value } });
    });
    styleSelect?.addEventListener("change", (event) => {
      patchState({ create: { style: event.target.value } });
    });
    referenceUrlInput?.addEventListener("input", (event) => {
      patchState({ create: { referenceUrl: event.target.value } });
    });

    existingProductSelect?.addEventListener("change", () => {
      const selected = existingProductSelect.options[existingProductSelect.selectedIndex];
      const name = selected?.value || "";
      const imageUrl = selected?.dataset.imageUrl || null;
      const description = selected?.dataset.description || "";
      patchState({ create: { selectedProductName: name, selectedProductImageUrl: imageUrl || null } });
      // 설명 프리필 (사용자가 직접 수정 가능)
      if (name && description && descriptionInput && !descriptionInput.value.trim()) {
        descriptionInput.value = description;
        patchState({ create: { productDescription: description } });
      }
      // 썸네일
      if (existingProductThumbWrap && existingProductThumb) {
        if (imageUrl) {
          existingProductThumb.src = imageUrl;
          existingProductThumbWrap.classList.remove("hidden");
        } else {
          existingProductThumbWrap.classList.add("hidden");
        }
      }
    });

    productImageTrigger?.addEventListener("click", () => productImageInput?.click());
    productImageInput?.addEventListener("change", async (event) => {
      const [file] = event.target.files || [];
      if (!file) return;
      const payload = await fileToPayload(file);
      patchState({ create: { productImage: payload } });
      if (productImageStatus) {
        productImageStatus.textContent = `${payload.name} 파일이 상품 사진으로 업로드 준비되었습니다.`;
      }
    });

    referenceTrigger?.addEventListener("click", () => referenceInput?.click());
    referenceInput?.addEventListener("change", async (event) => {
      const [file] = event.target.files || [];
      if (!file) return;
      const payload = await fileToPayload(file);
      patchState({ create: { referenceImage: payload } });
      if (referenceStatus) {
        referenceStatus.textContent = `${payload.name} 파일이 업로드 준비되었습니다.`;
      }
    });

    submitButton?.addEventListener("click", async () => {
      const latestState = readState();
      if (!latestState.create.productName.trim()) {
        setStatus(bootstrapStatus, "상품명을 먼저 입력해주세요.", "error");
        return;
      }
      if (latestState.create.isNewProduct && !latestState.create.productImage) {
        setStatus(bootstrapStatus, "신상품 사진을 먼저 업로드해주세요.", "error");
        return;
      }
      if (!latestState.create.isNewProduct && !latestState.create.selectedProductName) {
        setStatus(bootstrapStatus, "기존 상품을 선택하거나 신상품 토글을 켜주세요.", "error");
        return;
      }

      submitButton.disabled = true;
      setStatus(bootstrapStatus, "광고를 생성하는 중입니다. 잠시만 기다려주세요.", "loading");

      try {
        lastGenerateResult = await api("/generate", {
          method: "POST",
          body: {
            product_name: latestState.create.productName,
            description: latestState.create.productDescription,
            goal: latestState.create.goal,
            generation_type: latestState.create.generationType,
            tone: latestState.create.tone,
            style: latestState.create.style,
            is_new_product: latestState.create.isNewProduct,
            product_image: latestState.create.isNewProduct
              ? latestState.create.productImage
              : null,
            existing_product_name: latestState.create.isNewProduct
              ? null
              : latestState.create.selectedProductName || null,
            reference_url: latestState.create.referenceUrl,
            reference_image: latestState.create.referenceImage,
          },
        });
        lastCaptionResult = null;
        lastStoryResult = null;
        saveHistoryEntry(latestState.create, lastGenerateResult);
        renderGenerateResult(lastGenerateResult);
        setStatus(bootstrapStatus, "광고 생성이 완료되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      } finally {
        submitButton.disabled = false;
      }
    });

    regenerateButton?.addEventListener("click", () => {
      submitButton?.click();
    });

    captionButton?.addEventListener("click", async () => {
      if (!lastGenerateResult?.text_result?.ad_copies) {
        return;
      }
      setStatus(bootstrapStatus, "인스타그램 캡션을 만드는 중입니다.", "loading");
      try {
        const caption = await api("/caption", {
          method: "POST",
          body: {
            product_name: readState().create.productName,
            description: readState().create.productDescription,
            style: readState().create.tone,
            ad_copies: lastGenerateResult.text_result.ad_copies,
            is_new_product: Boolean(readState().create.isNewProduct),
          },
        });
        lastCaptionResult = caption;
        captionBlock.innerHTML = `
          <div class="result-card">
            <h3 class="result-card__title">피드 캡션</h3>
            <div class="copy-line" style="white-space:pre-wrap;">${escapeHtml(caption.caption)}</div>
            <div class="copy-line">${escapeHtml(caption.hashtags)}</div>
          </div>
        `;
        captionBlock.classList.remove("hidden");
        updateLastHistory({ captionReady: true });
        setStatus(bootstrapStatus, "피드 캡션이 준비되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      }
    });

    storyButton?.addEventListener("click", async () => {
      if (!lastGenerateResult?.image_data_url) {
        return;
      }
      const selectedStoryCopy = selectOne('input[name="story-copy"]:checked');
      const storyText = selectedStoryCopy?.value;
      if (!storyText) {
        setStatus(bootstrapStatus, "스토리 문구를 먼저 선택해주세요.", "error");
        return;
      }

      setStatus(bootstrapStatus, "스토리 이미지를 만드는 중입니다.", "loading");
      try {
        const story = await api("/story", {
          method: "POST",
          body: {
            image_data_url: lastGenerateResult.image_data_url,
            text: storyText,
          },
        });
        lastStoryResult = {
          ...story,
          text: storyText,
        };
        storyBlock.innerHTML = `
          <div class="result-card">
            <h3 class="result-card__title">스토리 이미지</h3>
            <img class="result-media" src="${story.image_data_url}" alt="스토리 이미지" />
            <a class="soft-button" style="margin-top:1rem;" href="${story.image_data_url}" download="brewgram-story.png">스토리 저장하기</a>
          </div>
        `;
        storyBlock.classList.remove("hidden");
        applyUploadButtonState();
        updateLastHistory({ storyReady: true });
        setStatus(bootstrapStatus, "스토리 이미지가 준비되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      }
    });

    uploadFeedButton?.addEventListener("click", async () => {
      const instagram = getInstagramSummary(lastBootstrap);
      if (!lastGenerateResult?.image_data_url) {
        setStatus(bootstrapStatus, "업로드할 피드 이미지를 먼저 생성해주세요.", "error");
        return;
      }
      if (instagram.expired || !instagram.upload_ready) {
        updateLastHistory({ uploadFeedStatus: "placeholder" });
        const nextNote = buildUploadPlaceholder(instagram, "feed");
        if (uploadNote) {
          uploadNote.innerHTML = nextNote.html;
          uploadNote.className = "upload-note";
          uploadNote.classList.remove("hidden");
        }
        setStatus(bootstrapStatus, nextNote.status, nextNote.tone);
        return;
      }

      setStatus(bootstrapStatus, "인스타그램 피드에 업로드하는 중입니다.", "loading");
      try {
        const latestState = readState();
        const response = await api("/upload/feed", {
          method: "POST",
          body: {
            product_name: latestState.create.productName,
            description: latestState.create.productDescription,
            goal: latestState.create.goal,
            caption: buildFeedUploadCaption(lastGenerateResult, lastCaptionResult, latestState),
            image_data_url: lastGenerateResult.image_data_url,
            generation_output_id: lastGenerateResult.generation_output_id,
          },
        });
        updateLastHistory({ uploadFeedStatus: "posted" });
        if (uploadNote) {
          const handle = response.account_username
            ? `@${escapeHtml(response.account_username)}`
            : "연결된 계정";
          uploadNote.innerHTML = `${handle} 계정으로 피드 업로드를 완료했습니다. 게시 ID: <b>${escapeHtml(response.instagram_post_id || "확인 중")}</b>`;
          uploadNote.className = "upload-note";
          uploadNote.classList.remove("hidden");
        }
        setStatus(bootstrapStatus, "인스타그램 피드 업로드가 완료되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      }
    });

    uploadStoryButton?.addEventListener("click", async () => {
      const instagram = getInstagramSummary(lastBootstrap);
      if (!lastStoryResult?.image_data_url) {
        setStatus(bootstrapStatus, "스토리 이미지를 먼저 만들어주세요.", "error");
        return;
      }
      if (instagram.expired || !instagram.upload_ready) {
        updateLastHistory({ uploadStoryStatus: "placeholder" });
        const nextNote = buildUploadPlaceholder(instagram, "story");
        if (uploadNote) {
          uploadNote.innerHTML = nextNote.html;
          uploadNote.className = "upload-note";
          uploadNote.classList.remove("hidden");
        }
        setStatus(bootstrapStatus, nextNote.status, nextNote.tone);
        return;
      }

      setStatus(bootstrapStatus, "인스타그램 스토리에 업로드하는 중입니다.", "loading");
      try {
        const response = await api("/upload/story", {
          method: "POST",
          body: {
            image_data_url: lastStoryResult.image_data_url,
            caption: lastStoryResult.text || "",
            generation_output_id: lastGenerateResult?.generation_output_id || null,
          },
        });
        updateLastHistory({ uploadStoryStatus: "posted" });
        if (uploadNote) {
          const handle = response.account_username
            ? `@${escapeHtml(response.account_username)}`
            : "연결된 계정";
          uploadNote.innerHTML = `${handle} 계정으로 스토리 업로드를 완료했습니다. 게시 ID: <b>${escapeHtml(response.instagram_post_id || "확인 중")}</b>`;
          uploadNote.className = "upload-note";
          uploadNote.classList.remove("hidden");
        }
        setStatus(bootstrapStatus, "인스타그램 스토리 업로드가 완료되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      }
    });

    selectOne("#create-back")?.addEventListener("click", () => {
      navigate(PATHS.home);
    });
  }

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    notifyPwaInstallStatusChange();
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    notifyPwaInstallStatusChange();
  });

  document.addEventListener("DOMContentLoaded", () => {
    registerPwaServiceWorker();
    if (PAGE === "welcome") bindWelcome();
    if (PAGE === "onboarding-1") bindStep1();
    if (PAGE === "onboarding-2") bindStep2();
    if (PAGE === "onboarding-3") bindStep3();
    if (PAGE === "onboarding-4") bindStep4();
    if (PAGE === "home") bindHome();
    if (PAGE === "archive") bindArchive();
    if (PAGE === "settings") bindSettings();
    if (PAGE === "create") bindCreate();
  });
})();
