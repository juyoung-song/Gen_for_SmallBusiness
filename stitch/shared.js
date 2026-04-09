(function () {
  const STORAGE_KEY = "brewgram.mobile.state.v1";
  const PAGE = document.body.dataset.stitchPage;
  const API_BASE = "/api/mobile";

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
  };

  let lastGenerateResult = null;

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
      neutral: "bg-surface-container-low text-on-surface-variant",
      loading: "bg-primary-container/40 text-primary",
      success: "bg-secondary-container/45 text-on-secondary-container",
      error: "bg-error-container/35 text-error",
    };

    node.className =
      "rounded-xl px-4 py-3 text-sm font-medium leading-relaxed " +
      (toneClassMap[tone] || toneClassMap.neutral);
    node.textContent = message;
    node.classList.remove("hidden");
  }

  function toggleTokens(element, tokens, enabled) {
    if (!tokens) return;
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
      window.location.href = "../2./code.html";
    });
    selectOne("#step1-prev")?.addEventListener("click", () => {
      window.location.href = "../index.html";
    });
    selectOne("#step1-back")?.addEventListener("click", () => {
      window.location.href = "../index.html";
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
      window.location.href = "../3./code.html";
    });
    selectOne("#step2-skip")?.addEventListener("click", () => {
      patchState({ onboarding: { instagramUrl: "", referenceImages: [] } });
      window.location.href = "../3./code.html";
    });
    selectOne("#step2-back")?.addEventListener("click", () => {
      window.location.href = "../1./code.html";
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
          result.status === "existing"
            ? "이미 저장된 브랜드가 있어서 기존 설정을 그대로 사용합니다."
            : "브랜드 세팅이 완료되었습니다. 메인 화면으로 이동합니다.",
          "success",
        );
        window.setTimeout(() => {
          window.location.href = "../4._2/code.html";
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
      window.location.href = "../2./code.html";
    });
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
    const textBlock = selectOne("#result-text-block");
    const imageBlock = selectOne("#result-image-block");
    const captionBlock = selectOne("#result-caption-block");
    const storyBlock = selectOne("#result-story-block");
    const actionRow = selectOne("#result-actions");
    const storyChooser = selectOne("#story-copy-chooser");
    const captionButton = selectOne("#create-caption-button");
    const storyButton = selectOne("#create-story-button");
    const canCaption = Boolean(result.text_result?.ad_copies?.length);
    const canStory = Boolean(
      result.image_data_url && (result.text_result?.story_copies || []).length,
    );

    wrap?.classList.remove("hidden");
    textBlock?.classList.add("hidden");
    imageBlock?.classList.add("hidden");
    captionBlock?.classList.add("hidden");
    storyBlock?.classList.add("hidden");
    actionRow?.classList.add("hidden");
    storyChooser?.classList.add("hidden");
    if (captionBlock) captionBlock.innerHTML = "";
    if (storyBlock) storyBlock.innerHTML = "";
    captionButton?.classList.toggle("hidden", !canCaption);
    storyButton?.classList.toggle("hidden", !canStory);
    if (captionButton) {
      captionButton.disabled = !canCaption;
    }
    if (storyButton) {
      storyButton.disabled = !canStory;
    }

    if (result.text_result && textBlock) {
      const adCopies = (result.text_result.ad_copies || [])
        .map((copy) => `<li class="rounded-xl bg-surface-container-highest px-4 py-3">${copy}</li>`)
        .join("");
      const promoSentences = (result.text_result.promo_sentences || [])
        .map((copy) => `<li class="rounded-xl bg-surface-container-highest px-4 py-3">${copy}</li>`)
        .join("");

      textBlock.innerHTML = `
        <div class="space-y-4">
          <h3 class="text-lg font-bold text-on-surface">생성된 홍보 문구</h3>
          <div class="space-y-3">
            <p class="text-sm font-semibold text-on-surface-variant">짧은 카피</p>
            <ul class="space-y-2 text-sm text-on-surface">${adCopies}</ul>
          </div>
          <div class="space-y-3">
            <p class="text-sm font-semibold text-on-surface-variant">상세 소개 문장</p>
            <ul class="space-y-2 text-sm text-on-surface">${promoSentences}</ul>
          </div>
        </div>
      `;
      textBlock.classList.remove("hidden");
    }

    if (result.image_data_url && imageBlock) {
      imageBlock.innerHTML = `
        <div class="space-y-4">
          <h3 class="text-lg font-bold text-on-surface">생성된 이미지</h3>
          <img class="w-full rounded-xl shadow-[0_18px_36px_rgba(55,50,34,0.10)]" src="${result.image_data_url}" alt="생성된 홍보 이미지" />
          <a class="inline-flex items-center justify-center rounded-full bg-primary px-5 py-3 text-sm font-bold text-on-primary" href="${result.image_data_url}" download="brewgram-ad.png">이미지 저장하기</a>
        </div>
      `;
      imageBlock.classList.remove("hidden");
    }

    if ((canCaption || canStory) && actionRow) {
      actionRow.classList.remove("hidden");
      const storyCopies = result.text_result.story_copies || [];
      if (canStory && storyCopies.length && storyChooser) {
        storyChooser.innerHTML = `
          <p class="text-sm font-semibold text-on-surface-variant mb-3">스토리 문구 선택</p>
          <div class="space-y-2">
            ${storyCopies
              .map(
                (copy, index) => `
                  <label class="flex items-center gap-3 rounded-xl bg-surface-container-highest px-4 py-3 text-sm text-on-surface">
                    <input ${index === 0 ? "checked" : ""} type="radio" name="story-copy" value="${copy.replace(/"/g, "&quot;")}" />
                    <span>${copy}</span>
                  </label>`,
              )
              .join("")}
          </div>
        `;
        storyChooser.classList.remove("hidden");
      }
    }
  }

  async function bindCreate() {
    const state = readState();
    const bootstrapStatus = selectOne("#create-status");

    try {
      const bootstrap = await api("/bootstrap");
      renderBrandSummary(bootstrap.brand, bootstrap);
      if (!bootstrap.onboarding_completed) {
        setStatus(
          bootstrapStatus,
          "브랜드 세팅이 아직 완료되지 않았습니다. 먼저 STEP 01부터 진행해주세요.",
          "error",
        );
      }
    } catch (error) {
      setStatus(bootstrapStatus, error.message, "error");
    }

    const productNameInput = selectOne("#create-product-name");
    const descriptionInput = selectOne("#create-product-description");
    const toneSelect = selectOne("#create-tone-select");
    const styleSelect = selectOne("#create-style-select");
    const referenceUrlInput = selectOne("#create-reference-url");
    const referenceTrigger = selectOne("#create-reference-trigger");
    const referenceInput = selectOne("#create-reference-input");
    const referenceStatus = selectOne("#create-reference-status");
    const submitButton = selectOne("#create-submit");
    const captionButton = selectOne("#create-caption-button");
    const storyButton = selectOne("#create-story-button");
    const captionBlock = selectOne("#result-caption-block");
    const storyBlock = selectOne("#result-story-block");

    productNameInput.value = state.create.productName || "";
    descriptionInput.value = state.create.productDescription || "";
    toneSelect.value = state.create.tone || "감성";
    styleSelect.value = state.create.style || "감성";
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
        renderGenerateResult(lastGenerateResult);
        setStatus(bootstrapStatus, "광고 생성이 완료되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      } finally {
        submitButton.disabled = false;
      }
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
          <div class="space-y-3">
            <h3 class="text-lg font-bold text-on-surface">피드 캡션</h3>
            <div class="rounded-xl bg-surface-container-highest px-4 py-4 text-sm leading-relaxed text-on-surface whitespace-pre-wrap">${caption.caption}</div>
            <div class="rounded-xl bg-surface-container-highest px-4 py-4 text-sm text-primary">${caption.hashtags}</div>
          </div>
        `;
        captionBlock.classList.remove("hidden");
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
          <div class="space-y-3">
            <h3 class="text-lg font-bold text-on-surface">스토리 이미지</h3>
            <img class="w-full rounded-xl shadow-[0_18px_36px_rgba(55,50,34,0.10)]" src="${story.image_data_url}" alt="스토리 이미지" />
            <a class="inline-flex items-center justify-center rounded-full bg-secondary-container px-5 py-3 text-sm font-bold text-on-secondary-container" href="${story.image_data_url}" download="brewgram-story.png">스토리 저장하기</a>
          </div>
        `;
        storyBlock.classList.remove("hidden");
        setStatus(bootstrapStatus, "스토리 이미지가 준비되었습니다.", "success");
      } catch (error) {
        setStatus(bootstrapStatus, error.message, "error");
      }
    });

    selectOne("#create-back")?.addEventListener("click", () => {
      window.location.href = "../3./code.html";
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (PAGE === "onboarding-1") bindStep1();
    if (PAGE === "onboarding-2") bindStep2();
    if (PAGE === "onboarding-3") bindStep3();
    if (PAGE === "create") bindCreate();
  });
})();
