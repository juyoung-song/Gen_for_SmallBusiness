(function () {
  const STORAGE_KEY = "brewgram.mobile.state.v1";
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

  const defaultState = {
    onboarding: {
      brandName: "",
      brandColor: "#ff7448",
      brandAtmosphere: "",
      brandDescription: "",
      instagramUrl: "",
      logo: null,
      referenceImages: [],
    },
    create: {
      productName: "",
      productDescription: "",
      goal: "신제품 출시",
      generationType: "both",
      tone: "감성",
      style: "감성",
      referenceUrl: "",
      referenceImage: null,
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
  let lastBootstrap = null;

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

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
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
      return "관리자 계정 준비";
    }
    if (summary.oauth_available) {
      return "미연결";
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
      return "현재는 관리자 고정 계정 업로드 환경만 준비되어 있습니다. 사장님 계정을 직접 연결하려면 Meta OAuth 설정이 필요합니다.";
    }
    if (summary.oauth_available) {
      return "사장님 본인 계정을 한 번만 연결해두면 이후 피드/스토리 업로드를 자연스럽게 이어붙일 수 있습니다.";
    }
    return "Meta OAuth 환경 설정이 아직 없어 개인 계정 연결 기능을 켤 수 없습니다.";
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
      return "이 화면이 계정 연결을 관리하는 유일한 진입점입니다. 홈과 결과 화면은 상태 요약과 연결 유도만 담당합니다.";
    }
    return "현재 환경에서는 개인 계정 연결이 비활성화되어 있습니다.";
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
      return "현재는 관리자 고정 계정 업로드 환경만 준비되어 있습니다. 사장님 계정 직접 연결은 설정에서 관리합니다.";
    }
    if (summary.oauth_available) {
      return "자동 업로드 기능은 아직 연결 전이지만, 설정에서 인스타그램 계정을 미리 연결해둘 수 있습니다.";
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
        html: `${handle} 계정 연결은 완료되었습니다. 자동 ${target} 업로드 API 연결만 남아 있어 지금은 저장 후 직접 업로드해 주세요.`,
        status: `${target} 자동 업로드 API는 아직 연결되지 않았습니다.`,
      };
    }
    return {
      tone: "neutral",
      html: `현재는 관리자 고정 계정 업로드 환경만 준비되어 있습니다. 사장님 계정으로 쓰려면 <a href="${PATHS.settings}">설정에서 연결</a>해 주세요.`,
      status: `${target} 업로드는 아직 개인 계정 연결 전입니다.`,
    };
  }

  function consumeInstagramFeedback() {
    const params = new URLSearchParams(window.location.search);
    const flag = params.get("ig");
    if (!flag) return null;

    const message = params.get("ig_message");
    clearQueryFromCurrentPath();

    if (flag === "connected") {
      return {
        tone: "success",
        message: "인스타그램 계정 연결이 완료되었습니다.",
      };
    }
    if (flag === "cancelled") {
      return {
        tone: "neutral",
        message: "인스타그램 계정 연결이 취소되었습니다.",
      };
    }
    return {
      tone: "error",
      message: message || "인스타그램 계정 연결 중 오류가 발생했습니다.",
    };
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

  function buildHistoryEntry(createState, result) {
    const copies = result.text_result?.ad_copies || [];
    return {
      id: `hist_${Date.now()}`,
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
          item.uploadStoryStatus === "placeholder" ? "스토리 업로드 준비" : null,
        ].filter(Boolean);
        const status =
          item.uploadFeedStatus === "placeholder" || item.uploadStoryStatus === "placeholder"
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

  function bindStep1() {
    const state = readState();
    const brandNameInput = selectOne("#brand-name-input");
    const atmosphereInput = selectOne("#brand-atmosphere-input");
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

    setActiveColor(state.onboarding.brandColor);

    if (state.onboarding.logo?.name && logoName) {
      logoName.textContent = state.onboarding.logo.name;
    }

    brandNameInput?.addEventListener("input", (event) => {
      patchState({ onboarding: { brandName: event.target.value } });
    });

    atmosphereInput?.addEventListener("input", (event) => {
      patchState({ onboarding: { brandAtmosphere: event.target.value } });
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
    const skipButton = selectOne("#step3-skip");
    const statusNode = selectOne("#onboarding-status");

    descriptionInput.value = state.onboarding.brandDescription || "";
    descriptionInput?.addEventListener("input", (event) => {
      patchState({ onboarding: { brandDescription: event.target.value } });
    });

    const submit = async (skipDescription) => {
      const nextState = patchState({
        onboarding: {
          brandDescription: skipDescription ? "" : descriptionInput.value,
        },
      });

      submitButton.disabled = true;
      skipButton.disabled = true;
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
        setStatus(
          statusNode,
          result.status === "updated"
            ? "브랜드 정보를 새 입력값으로 업데이트했습니다. 마지막 연결 단계로 이동합니다."
            : result.status === "existing"
              ? "이미 저장된 브랜드가 있어 기존 설정을 그대로 사용합니다. 마지막 연결 단계로 이동합니다."
              : "브랜드 세팅이 완료되었습니다. 마지막 연결 단계로 이동합니다.",
          "success",
        );
        window.setTimeout(() => {
          navigate(PATHS.onboarding4);
        }, 700);
      } catch (error) {
        setStatus(statusNode, error.message, "error");
      } finally {
        submitButton.disabled = false;
        skipButton.disabled = false;
      }
    };

    submitButton?.addEventListener("click", () => submit(false));
    skipButton?.addEventListener("click", () => submit(true));
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
            "지금 연결해두면 이후 업로드 기능이 붙었을 때 더 자연스럽게 이어집니다. 원하지 않으면 건너뛰어도 됩니다.";
        } else {
          copyNode.textContent =
            "현재 환경에서는 계정 연결을 사용할 수 없습니다. 나중에 설정이 준비되면 설정 화면에서 연결할 수 있습니다.";
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
          !bootstrap?.onboarding_completed || !summary.oauth_available || summary.connected,
        );
        connectButton.textContent = summary.expired ? "다시 연결하기" : "인스타 계정 연결";
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
        window.location.assign(response.url);
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
      if (uploadFeedButton) uploadFeedButton.disabled = !result.image_data_url;
      if (uploadStoryButton) uploadStoryButton.disabled = !result.image_data_url;
      uploadFeedButton?.classList.toggle("action-button--disabled", !result.image_data_url);
      uploadStoryButton?.classList.toggle("action-button--disabled", !result.image_data_url);
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

      const canConnect = onboardingCompleted && instagram.oauth_available && !instagram.connected && !instagram.expired;
      const canReconnect = onboardingCompleted && instagram.oauth_available && (instagram.connected || instagram.expired);
      const canDisconnect = onboardingCompleted && (instagram.connected || instagram.expired);

      instagramConnectButton?.classList.toggle("hidden", !canConnect);
      instagramReconnectButton?.classList.toggle("hidden", !canReconnect);
      instagramDisconnectButton?.classList.toggle("hidden", !canDisconnect);
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
        window.location.assign(response.url);
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
        window.location.assign(response.url);
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

    try {
      const payload = await loadSettingsStatus();
      if (!payload) return;
      if (feedback) {
        setStatus(statusNode, feedback.message, feedback.tone);
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

    applyGoalStyles(state.create.goal);
    applyGenerationStyles(state.create.generationType);

    goalButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.goalChoice;
        patchState({ create: { goal: value } });
        applyGoalStyles(value);
        if (customGoalInput) {
          customGoalInput.value = "";
        }
      });
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
      const nextGoal = event.target.value.trim() || PRESET_GOALS[0];
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
            reference_url: latestState.create.referenceUrl,
            reference_image: latestState.create.referenceImage,
          },
        });
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
          },
        });
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
        storyBlock.innerHTML = `
          <div class="result-card">
            <h3 class="result-card__title">스토리 이미지</h3>
            <img class="result-media" src="${story.image_data_url}" alt="스토리 이미지" />
            <a class="soft-button" style="margin-top:1rem;" href="${story.image_data_url}" download="brewgram-story.png">스토리 저장하기</a>
          </div>
        `;
        storyBlock.classList.remove("hidden");
        updateLastHistory({ storyReady: true });
        setStatus(bootstrapStatus, "스토리 이미지가 준비되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      }
    });

    uploadFeedButton?.addEventListener("click", () => {
      updateLastHistory({ uploadFeedStatus: "placeholder" });
      const nextNote = buildUploadPlaceholder(getInstagramSummary(lastBootstrap), "feed");
      if (uploadNote) {
        uploadNote.innerHTML = nextNote.html;
        uploadNote.className = "upload-note";
        uploadNote.classList.remove("hidden");
      }
      setStatus(bootstrapStatus, nextNote.status, nextNote.tone);
    });

    uploadStoryButton?.addEventListener("click", () => {
      updateLastHistory({ uploadStoryStatus: "placeholder" });
      const nextNote = buildUploadPlaceholder(getInstagramSummary(lastBootstrap), "story");
      if (uploadNote) {
        uploadNote.innerHTML = nextNote.html;
        uploadNote.className = "upload-note";
        uploadNote.classList.remove("hidden");
      }
      setStatus(bootstrapStatus, nextNote.status, nextNote.tone);
    });

    selectOne("#create-back")?.addEventListener("click", () => {
      navigate(PATHS.home);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
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
