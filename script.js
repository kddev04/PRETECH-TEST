/* =========================================================
   Pretech Automation — interactions and the 3D cell
   Classic script: the page still works opened straight from disk.
   three.js r186 is pulled in with dynamic import() through the import map.
   ========================================================= */

/* ---------------------------------------------------------
   1. Page UI
   --------------------------------------------------------- */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const WA_NUMBER = "919422310821";
  const EMAIL = "shriram.sampagaonkar@pretech.co.in";

  const whenVisible = (el, onChange) => {
    if (!el || !("IntersectionObserver" in window)) { onChange(true); return; }
    new IntersectionObserver(([entry]) => onChange(entry.isIntersecting), { threshold: 0.05 }).observe(el);
  };

  /* footer year */
  const year = $("#year");
  if (year) year.textContent = String(new Date().getFullYear());

  /* mobile menu */
  const menuBtn = $("#menuBtn");
  const nav = $("#nav");
  const setMenu = (open) => {
    menuBtn.setAttribute("aria-expanded", String(open));
    menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    nav.classList.toggle("open", open);
  };
  menuBtn.addEventListener("click", () => setMenu(menuBtn.getAttribute("aria-expanded") !== "true"));
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });
  document.addEventListener("click", (e) => {
    if (nav.classList.contains("open") && !e.target.closest("#nav, #menuBtn")) setMenu(false);
  });

  /* scroll spy */
  const navLinks = $$('.nav a[href^="#"]:not(.nav-cta)');
  const linkFor = new Map(navLinks.map((a) => [a.getAttribute("href").slice(1), a]));
  if ("IntersectionObserver" in window) {
    const spy = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navLinks.forEach((l) => { l.classList.remove("is-current"); l.removeAttribute("aria-current"); });
        const link = linkFor.get(entry.target.id);
        if (link) { link.classList.add("is-current"); link.setAttribute("aria-current", "true"); }
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    $$("main section[id]").forEach((s) => spy.observe(s));
  }

  /* ISA-95 stack linked to the discipline list */
  const layered = $$(".plate, .stack-labels li");
  const discs = $$(".disc");
  const stackWrap = $(".stack-wrap");
  const activate = (layer) => {
    layered.forEach((p) => p.classList.toggle("is-active", p.dataset.layer === layer));
    discs.forEach((d) => d.classList.toggle("is-active", d.dataset.layer === layer));
  };
  discs.forEach((d) => {
    d.addEventListener("mouseenter", () => activate(d.dataset.layer));
    d.addEventListener("focus", () => activate(d.dataset.layer));
  });
  const list = $(".disciplines");
  if (list) {
    list.addEventListener("mouseleave", () => activate(null));
    list.addEventListener("focusout", (e) => { if (!list.contains(e.relatedTarget)) activate(null); });
  }
  whenVisible(stackWrap, (visible) => stackWrap && stackWrap.classList.toggle("is-paused", !visible));

  /* automation tabs */
  const tabs = $$('#autoTabs [role="tab"]');
  const selectTab = (tab, focus) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
    });
    if (focus) tab.focus();
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(tab, false));
    tab.addEventListener("keydown", (e) => {
      let next = null;
      if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (e.key === "Home") next = tabs[0];
      if (e.key === "End") next = tabs[tabs.length - 1];
      if (next) { e.preventDefault(); selectTab(next, true); }
    });
  });

  /* client filter */
  const filters = $$(".filter");
  const logos = $$("#logos li");
  filters.forEach((btn) => {
    btn.addEventListener("click", () => {
      const cat = btn.dataset.filter;
      filters.forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      logos.forEach((li) => {
        const show = cat === "all" || li.dataset.cat === cat;
        li.hidden = !show;
        li.classList.remove("is-in");
        if (show && !reduceMotion) { void li.offsetWidth; li.classList.add("is-in"); }
      });
    });
  });

  /* IIoT sample chart */
  const chart = $("#utilChart");
  if (chart) {
    const data = [71, 74, 73, 76, 79, 75, 72, 78, 81, 80, 77, 82, 84, 83];
    const W = 400, H = 176, L = 36, R = 8, T = 8, B = 28;
    const yMin = 60, yMax = 100, target = 80;
    const x = (i) => L + (i / (data.length - 1)) * (W - L - R);
    const y = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
    const NS = "http://www.w3.org/2000/svg";
    const el = (name, attrs, text) => {
      const n = document.createElementNS(NS, name);
      Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
      if (text) n.textContent = text;
      chart.appendChild(n);
      return n;
    };
    [60, 70, 80, 90, 100].forEach((v) => {
      el("line", { class: "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) });
      el("text", { class: "axis", x: L - 8, y: y(v) + 4, "text-anchor": "end" }, v + "%");
    });
    el("line", { class: "target", x1: L, x2: W - R, y1: y(target), y2: y(target) });
    const fmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
    const today = new Date();
    [0, 7, data.length - 1].forEach((i) => {
      const d = new Date(today);
      d.setDate(today.getDate() - (data.length - 1 - i));
      const anchor = i === 0 ? "start" : i === data.length - 1 ? "end" : "middle";
      el("text", { class: "axis", x: x(i), y: H - 6, "text-anchor": anchor }, fmt.format(d));
    });
    el("polyline", { class: "line", points: data.map((v, i) => `${x(i)},${y(v)}`).join(" ") });
    const last = data.length - 1;
    el("circle", { class: "dot", cx: x(last), cy: y(data[last]), r: 4.5 });
  }

  /* contact form: email or WhatsApp, no backend needed */
  const form = $("#contactForm");
  if (form) {
    const note = $("#formNote");
    let via = "email";
    $$('button[type="submit"]', form).forEach((b) => b.addEventListener("click", () => { via = b.dataset.via; }));
    const fields = {
      name: { input: $("#f-name"), err: $("#e-name") },
      email: { input: $("#f-email"), err: $("#e-email") },
      mobile: { input: $("#f-mobile"), err: $("#e-mobile") },
      message: { input: $("#f-msg"), err: $("#e-msg") },
    };
    const setError = (key, msg) => {
      const f = fields[key];
      f.err.textContent = msg || "";
      if (msg) { f.input.setAttribute("aria-invalid", "true"); f.input.setAttribute("aria-describedby", f.err.id); }
      else { f.input.removeAttribute("aria-invalid"); f.input.removeAttribute("aria-describedby"); }
    };
    Object.keys(fields).forEach((k) => fields[k].input.addEventListener("input", () => setError(k, "")));

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = fields.name.input.value.trim();
      const company = $("#f-company").value.trim();
      const email = fields.email.input.value.trim();
      const mobile = fields.mobile.input.value.trim();
      const message = fields.message.input.value.trim();

      const errors = {};
      if (!name) errors.name = "Enter your name";
      if (via === "email" && !email) errors.email = "Enter your email so we can reply";
      else if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) errors.email = "Check the email address";
      if (mobile && !/^\+?[\d\s()-]{7,}$/.test(mobile)) errors.mobile = "Check the mobile number";
      if (message.length < 10) errors.message = "Tell us a little about the project";

      Object.keys(fields).forEach((k) => setError(k, errors[k]));
      const firstBad = Object.keys(fields).find((k) => errors[k]);
      if (firstBad) { fields[firstBad].input.focus(); note.textContent = ""; return; }

      const body = [
        `Name: ${name}`,
        company ? `Company: ${company}` : null,
        email ? `Email: ${email}` : null,
        mobile ? `Mobile: ${mobile}` : null,
        "",
        message,
      ].filter((l) => l !== null).join("\n");

      if (via === "whatsapp") {
        window.open(`https://wa.me/${WA_NUMBER}?text=${encodeURIComponent("Hello Pretech,\n\n" + body)}`, "_blank", "noopener");
        note.textContent = "WhatsApp opened in a new tab with your message ready to send.";
      } else {
        const subject = `Project enquiry from ${name}${company ? ", " + company : ""}`;
        window.location.href = `mailto:${EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
        note.textContent = `Your email app should open with the message ready. If it doesn't, write to ${EMAIL}.`;
      }
    });
  }
})();

/* ---------------------------------------------------------
   2. Hero: a live robotic palletising cell (three.js r186)
   Everything is procedural. Units are metres, +Y up.
   --------------------------------------------------------- */
(async () => {
  "use strict";

  const canvas = document.getElementById("cell");
  const hero = document.getElementById("hero");
  const calloutLayer = document.getElementById("callouts");
  if (!canvas || !hero) return;

  const noScene = (err) => {
    document.documentElement.classList.add("no-3d");
    if (err) console.warn("Pretech 3D cell unavailable:", err);
  };

  let THREE, RoomEnvironment, RoundedBoxGeometry;
  try {
    THREE = await import("three");
    ({ RoomEnvironment } = await import("three/addons/environments/RoomEnvironment.js"));
    ({ RoundedBoxGeometry } = await import("three/addons/geometries/RoundedBoxGeometry.js"));
  } catch (err) { noScene(err); return; }

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  } catch (err) { noScene(err); return; }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const small = window.matchMedia("(max-width: 900px)");
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, small.matches ? 1.5 : 1.75));
  renderer.toneMapping = THREE.NeutralToneMapping; // keeps the brand orange true
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;

  /* ---------- scene, environment, fog ---------- */
  const BG = 0x0b0d11;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BG);
  scene.fog = new THREE.Fog(BG, 12, 30);
  {
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    scene.environment = pmrem.fromScene(room, 0.04).texture;
    scene.environmentIntensity = 0.38;
    room.dispose();
    pmrem.dispose();
  }

  /* ---------- lights ---------- */
  const key = new THREE.DirectionalLight(0xfff3e4, 2.4);
  key.position.set(5.5, 9, 6.5);
  key.castShadow = true;
  key.shadow.mapSize.set(small.matches ? 1024 : 2048, small.matches ? 1024 : 2048);
  Object.assign(key.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: 2, far: 28 });
  key.shadow.camera.updateProjectionMatrix();
  key.shadow.normalBias = 0.02;
  key.shadow.bias = -0.0002;
  key.shadow.intensity = 0.85;
  scene.add(key);

  const rim = new THREE.DirectionalLight(0xc4d4ff, 1.1); // cool back light separates the arm from the dark
  rim.position.set(-6, 5, -7);
  scene.add(rim);

  const bay = new THREE.SpotLight(0xfff1dc, 140, 16, 0.62, 0.75, 2); // high-bay light over the cell (candela)
  bay.position.set(0.8, 7, 0.6);
  bay.target.position.set(0.8, 0, 0.4);
  scene.add(bay, bay.target);

  /* ---------- materials ---------- */
  const M = {
    paint: new THREE.MeshPhysicalMaterial({ color: 0xf48516, roughness: 0.34, metalness: 0.05, clearcoat: 0.7, clearcoatRoughness: 0.18 }),
    graphite: new THREE.MeshStandardMaterial({ color: 0x2b2e34, roughness: 0.48, metalness: 0.55 }),
    black: new THREE.MeshStandardMaterial({ color: 0x141619, roughness: 0.62, metalness: 0.2 }),
    steel: new THREE.MeshStandardMaterial({ color: 0xd0d4d9, roughness: 0.24, metalness: 1 }),
    jacket: new THREE.MeshStandardMaterial({ color: 0xb9bec4, roughness: 0.36, metalness: 1 }),
    alu: new THREE.MeshStandardMaterial({ color: 0xaab0b7, roughness: 0.42, metalness: 0.95 }),
    ral7035: new THREE.MeshStandardMaterial({ color: 0xd1d2cc, roughness: 0.55, metalness: 0.08 }),
    floor: new THREE.MeshStandardMaterial({ color: 0x171a1f, roughness: 0.38, metalness: 0 }),
    card: new THREE.MeshStandardMaterial({ color: 0xab7c4b, roughness: 0.92 }),
    wood: new THREE.MeshStandardMaterial({ color: 0x8c6c46, roughness: 0.9 }),
    yellow: new THREE.MeshStandardMaterial({ color: 0xf2c230, roughness: 0.5, metalness: 0.1 }),
    rubber: new THREE.MeshStandardMaterial({ color: 0x0e0f11, roughness: 0.9 }),
    ledGreen: new THREE.MeshBasicMaterial({ color: 0x3ee089, toneMapped: false }),
    ledAmberOff: new THREE.MeshStandardMaterial({ color: 0x5a4416, roughness: 0.3 }),
    ledRedOff: new THREE.MeshStandardMaterial({ color: 0x4a1714, roughness: 0.3 }),
    ledOrange: new THREE.MeshBasicMaterial({ color: 0xff9a3c, toneMapped: false }),
    bayLight: new THREE.MeshBasicMaterial({ color: 0xfff6e8, toneMapped: false }),
  };

  /* ---------- helpers ---------- */
  const add = (parent, geometry, material, x = 0, y = 0, z = 0, shadow = true) => {
    const m = new THREE.Mesh(geometry, material);
    m.position.set(x, y, z);
    m.castShadow = shadow;
    m.receiveShadow = shadow;
    parent.add(m);
    return m;
  };
  const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  const rbox = (w, h, d, r = 0.03) => new RoundedBoxGeometry(w, h, d, 3, r);
  const cyl = (rt, rb, h, seg = 32) => new THREE.CylinderGeometry(rt, rb, h, seg);
  const cylX = (r, len, seg = 32) => cyl(r, r, len, seg).rotateZ(Math.PI / 2); // axis along X
  const cylZ = (r, len, seg = 32) => cyl(r, r, len, seg).rotateX(Math.PI / 2); // axis along Z
  const canvasTexture = (w, h, draw) => {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    draw(ctx, w, h);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = renderer.capabilities.getMaxAnisotropy();
    return { texture: t, ctx, canvas: c };
  };
  await Promise.race([document.fonts ? document.fonts.ready : Promise.resolve(), new Promise((r) => setTimeout(r, 1200))]);
  const FONT = '"IBM Plex Sans", "Segoe UI", sans-serif';
  const MONO = '"IBM Plex Mono", Consolas, monospace';

  /* ---------- floor, hazard border, factory bay ---------- */
  const floor = add(scene, new THREE.PlaneGeometry(80, 80), M.floor, 0, 0, 0, false);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;

  const hazard = canvasTexture(128, 32, (ctx, w, h) => {
    ctx.fillStyle = "#15181d"; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#e9b82a";
    for (let x = -h; x < w + h; x += 32) {
      ctx.beginPath(); ctx.moveTo(x, h); ctx.lineTo(x + 16, h); ctx.lineTo(x + 16 + h, 0); ctx.lineTo(x + h, 0); ctx.closePath(); ctx.fill();
    }
  }).texture;
  hazard.wrapS = THREE.RepeatWrapping;
  const zone = { x0: -0.95, x1: 2.95, z0: -0.7, z1: 2.15 };
  const tape = (x0, z0, x1, z1) => {
    const len = Math.hypot(x1 - x0, z1 - z0);
    const t = hazard.clone();
    t.repeat.set(len / 0.32, 1);
    t.needsUpdate = true;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(len, 0.08), new THREE.MeshStandardMaterial({ map: t, roughness: 0.6 }));
    m.rotation.x = -Math.PI / 2;
    m.rotation.z = -Math.atan2(z1 - z0, x1 - x0);
    m.position.set((x0 + x1) / 2, 0.003, (z0 + z1) / 2);
    m.receiveShadow = true;
    scene.add(m);
  };
  tape(zone.x0, zone.z0, zone.x1, zone.z0);
  tape(zone.x1, zone.z0, zone.x1, zone.z1);
  tape(zone.x0, zone.z1, zone.x1, zone.z1);
  tape(zone.x0, zone.z0, zone.x0, zone.z1);

  // bay lights and columns far behind, softened by fog
  for (let i = 0; i < 6; i++) {
    add(scene, box(2.4, 0.05, 0.22), M.bayLight, -6 + i * 3.2, 6.4, -5.5, false);
    add(scene, box(2.4, 0.05, 0.22), M.bayLight, -6 + i * 3.2, 6.4, 0.5, false);
  }
  for (let i = 0; i < 5; i++) add(scene, box(0.32, 8, 0.32), M.graphite, -7 + i * 4, 4, -7, false);

  /* ---------- 6-axis robot ---------- */
  const BASE_TOP = 0.57;  // top of the base housing
  const SH_Y = 0.43;      // shoulder axis above J1 frame
  const H = BASE_TOP + SH_Y; // shoulder height in world: 1.00 m
  const A1 = 0.18;        // shoulder offset from the J1 axis
  const L1 = 1.05;        // upper arm
  const L2 = 1.1;         // forearm, elbow to wrist axis
  const TOOL = 0.32;      // wrist axis to suction-cup face

  const robot = new THREE.Group();
  scene.add(robot);
  add(robot, box(1.1, 0.04, 1.1), M.graphite, 0, 0.02, 0);
  add(robot, cyl(0.46, 0.5, 0.21, 48), M.graphite, 0, 0.145, 0);
  add(robot, cyl(0.37, 0.41, 0.32, 48), M.paint, 0, 0.41, 0);
  for (let i = 0; i < 4; i++) {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    add(robot, cyl(0.035, 0.035, 0.05, 12), M.alu, Math.cos(a) * 0.48, 0.065, Math.sin(a) * 0.48);
  }

  const j1 = new THREE.Group();
  j1.position.y = BASE_TOP;
  robot.add(j1);
  add(j1, rbox(0.62, 0.5, 0.74, 0.07), M.paint, 0, 0.24, 0.04);
  add(j1, rbox(0.24, 0.24, 0.3, 0.04), M.graphite, 0, 0.36, -0.42); // J2 motor at the back
  add(j1, cylX(0.23, 0.7, 40), M.graphite, 0, SH_Y, A1);
  add(j1, cylX(0.16, 0.74, 32), M.alu, 0, SH_Y, A1);

  const shoulder = new THREE.Group();
  shoulder.position.set(0, SH_Y, A1);
  j1.add(shoulder);
  add(shoulder, rbox(0.27, 0.36, L1 + 0.34, 0.09), M.paint, 0, 0, L1 / 2);
  // brand plate on the upper arm
  const plate = canvasTexture(512, 96, (ctx, w, h) => {
    ctx.fillStyle = "#1d2025"; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#f2f0eb"; ctx.font = `600 54px ${FONT}`; ctx.textBaseline = "middle";
    ctx.fillText("PRETECH", 28, h / 2 + 2);
    ctx.fillStyle = "#f48516"; ctx.fillRect(w - 64, 24, 36, 48);
  }).texture;
  const brandMat = new THREE.MeshStandardMaterial({ map: plate, roughness: 0.4, metalness: 0.2 });
  const brandL = add(shoulder, new THREE.PlaneGeometry(0.52, 0.098), brandMat, 0.137, 0.02, L1 * 0.52, false);
  brandL.rotation.set(0, Math.PI / 2, 0); // faces +X, reads along the arm
  const brandR = add(shoulder, new THREE.PlaneGeometry(0.52, 0.098), brandMat, -0.137, 0.02, L1 * 0.52, false);
  brandR.rotation.set(0, -Math.PI / 2, 0);
  // dress pack cable along the arm
  const cable = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.17, -0.08, -0.2), new THREE.Vector3(0.2, 0.0, 0.3),
    new THREE.Vector3(0.19, 0.08, 0.75), new THREE.Vector3(0.16, 0.12, L1),
  ]);
  add(shoulder, new THREE.TubeGeometry(cable, 40, 0.026, 10, false), M.black, 0, 0, 0);

  const elbow = new THREE.Group();
  elbow.position.set(0, 0, L1);
  shoulder.add(elbow);
  add(elbow, cylX(0.2, 0.42, 40), M.paint, 0, 0, 0);
  add(elbow, cylX(0.12, 0.48, 28), M.graphite, 0, 0, 0);
  add(elbow, rbox(0.27, 0.3, 0.38, 0.05), M.graphite, 0, 0.04, -0.24); // forearm motors
  add(elbow, rbox(0.21, 0.23, L2 - 0.02, 0.07), M.paint, 0, 0, L2 / 2);
  add(elbow, cylZ(0.105, 0.24, 32), M.paint, 0, 0, L2 - 0.16);

  const wrist = new THREE.Group();
  wrist.position.set(0, 0, L2);
  elbow.add(wrist);
  add(wrist, cylX(0.1, 0.25, 32), M.paint, 0, 0, 0);
  add(wrist, cylX(0.065, 0.28, 24), M.graphite, 0, 0, 0);
  add(wrist, cylZ(0.075, 0.1, 32), M.graphite, 0, 0, 0.07);

  const j6 = new THREE.Group();
  j6.position.set(0, 0, 0.12);
  wrist.add(j6);
  add(j6, cylZ(0.045, 0.06, 20), M.alu, 0, 0, 0.03);
  add(j6, rbox(0.4, 0.4, 0.032, 0.012), M.alu, 0, 0, 0.075);
  add(j6, box(0.36, 0.05, 0.05), M.graphite, 0, 0, 0.1);
  for (const [cx, cy] of [[0.13, 0.13], [-0.13, 0.13], [0.13, -0.13], [-0.13, -0.13]]) {
    add(j6, cylZ(0.022, 0.07, 14), M.alu, cx, cy, 0.125);
    add(j6, new THREE.CylinderGeometry(0.05, 0.035, 0.04, 20).rotateX(Math.PI / 2), M.rubber, cx, cy, 0.18);
  }
  const vacLed = add(j6, box(0.05, 0.02, 0.02), M.ledAmberOff, 0.19, 0, 0.075, false);
  const tip = new THREE.Object3D();
  tip.position.set(0, 0, 0.2);
  j6.add(tip);

  // analytic inverse kinematics: tool pointing straight down, elbow up
  const joints = { t1: 0, t2: 0, t3: 0, t5: 0, t6: 0 };
  const solveIK = (target, yaw) => {
    const wx = target.x, wy = target.y + TOOL, wz = target.z;
    const t1 = Math.atan2(wx, wz);
    const r = Math.hypot(wx, wz) - A1;
    const s = wy - H;
    const D = THREE.MathUtils.clamp((r * r + s * s - L1 * L1 - L2 * L2) / (2 * L1 * L2), -1, 1);
    const t3 = -Math.acos(D);
    const t2 = Math.atan2(s, r) - Math.atan2(L2 * Math.sin(t3), L1 + L2 * Math.cos(t3));
    const t5 = -Math.PI / 2 - t2 - t3;
    joints.t1 = t1; joints.t2 = t2; joints.t3 = t3; joints.t5 = t5; joints.t6 = t1 - yaw;
    j1.rotation.y = t1;
    shoulder.rotation.x = -t2;
    elbow.rotation.x = -t3;
    wrist.rotation.x = -t5;
    j6.rotation.z = joints.t6;
  };

  /* ---------- robot controller cabinet ---------- */
  const ctrl = new THREE.Group();
  ctrl.position.set(-0.55, 0, -0.35);
  ctrl.rotation.y = 0.5;
  scene.add(ctrl);
  add(ctrl, rbox(0.62, 1.05, 0.5, 0.02), M.graphite, 0, 0.6, 0);
  add(ctrl, box(0.64, 0.08, 0.52), M.black, 0, 0.04, 0);
  add(ctrl, box(0.5, 0.02, 0.012), M.ledGreen, 0, 0.98, 0.252, false);
  add(ctrl, rbox(0.16, 0.26, 0.05, 0.015), M.black, 0.22, 0.75, 0.29); // teach pendant

  /* ---------- roller conveyor CV-101 ---------- */
  const CZ = 1.65, CY = 0.72, X0 = -5.4, X1 = 0.42;
  const conveyor = new THREE.Group();
  scene.add(conveyor);
  const cLen = X1 - X0;
  for (const side of [-1, 1]) {
    add(conveyor, box(cLen, 0.12, 0.05), M.alu, (X0 + X1) / 2, CY - 0.05, CZ + side * 0.34);
    for (let x = X0 + 0.3; x < X1; x += 1.1) add(conveyor, box(0.05, CY - 0.1, 0.05), M.alu, x, (CY - 0.1) / 2, CZ + side * 0.3);
  }
  const rollerGeo = cyl(0.034, 0.034, 0.62, 18).rotateX(Math.PI / 2);
  const rollerCount = Math.floor(cLen / 0.1);
  const rollers = new THREE.InstancedMesh(rollerGeo, M.steel, rollerCount);
  rollers.castShadow = true; rollers.receiveShadow = true;
  conveyor.add(rollers);
  const dummy = new THREE.Object3D();
  let rollerAngle = 0;
  const placeRollers = () => {
    for (let i = 0; i < rollerCount; i++) {
      dummy.position.set(X0 + 0.05 + i * 0.1, CY - 0.034, CZ);
      dummy.rotation.set(0, 0, -rollerAngle);
      dummy.updateMatrix();
      rollers.setMatrixAt(i, dummy.matrix);
    }
    rollers.instanceMatrix.needsUpdate = true;
  };
  placeRollers();
  rollers.computeBoundingSphere();
  add(conveyor, box(0.06, 0.12, 0.66), M.yellow, X1 + 0.03, CY + 0.04, CZ); // end stop
  // photo-eye at the pick position
  add(conveyor, box(0.05, 0.1, 0.05), M.graphite, 0.12, CY + 0.1, CZ - 0.4);
  const eyeLed = add(conveyor, box(0.02, 0.02, 0.012), M.ledAmberOff, 0.12, CY + 0.13, CZ - 0.37, false);
  // light curtain posts where the conveyor enters the cell
  for (const side of [-1, 1]) {
    add(conveyor, box(0.06, 1.5, 0.06), M.yellow, zone.x0, 0.75, CZ + side * 0.46);
    add(conveyor, box(0.012, 1.2, 0.012), M.ledGreen, zone.x0, 0.8, CZ + side * 0.425, false);
  }

  /* ---------- cartons ---------- */
  const CW = 0.54, CH = 0.3, CD = 0.42;
  const cartonTop = canvasTexture(256, 200, (ctx, w, h) => {
    ctx.fillStyle = "#b5874f"; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#c9a26b"; ctx.fillRect(0, h / 2 - 16, w, 32); // tape
    ctx.fillStyle = "#f3f0e8"; ctx.fillRect(w - 104, h - 72, 88, 56); // label
    ctx.fillStyle = "#2a2522";
    for (let i = 0; i < 4; i++) ctx.fillRect(w - 96, h - 64 + i * 11, 40 + (i % 2) * 24, 4);
    ctx.fillStyle = "#f48516"; ctx.fillRect(w - 34, h - 64, 10, 10);
  }).texture;
  const cartonTopMat = new THREE.MeshStandardMaterial({ map: cartonTop, roughness: 0.9 });
  const cartonMats = [M.card, M.card, cartonTopMat, M.card, M.card, M.card];
  const cartonGeo = box(CW, CH, CD);
  const pool = [];
  const makeCarton = () => {
    const m = new THREE.Mesh(cartonGeo, cartonMats);
    m.castShadow = true; m.receiveShadow = true;
    m.visible = false;
    scene.add(m);
    return { mesh: m, x: 0, state: "free" };
  };
  for (let i = 0; i < 16; i++) pool.push(makeCarton());
  const takeCarton = () => pool.find((c) => c.state === "free");

  const PICKX = 0.12;
  const SPAWNX = X0 + 0.4;
  const GAP = CW + 0.08;
  const belt = []; // front first
  const spawn = (x) => {
    const c = takeCarton();
    if (!c) return;
    c.state = "belt"; c.x = x;
    c.mesh.visible = true;
    scene.attach(c.mesh);
    c.mesh.rotation.set(0, 0, 0);
    c.mesh.position.set(x, CY + CH / 2, CZ);
    belt.push(c);
  };
  [PICKX, PICKX - 1.1, PICKX - 2.6].forEach(spawn);

  /* ---------- AGV with pallet ---------- */
  const AGV_HOME = new THREE.Vector3(1.8, 0, 0.28);
  const agv = new THREE.Group();
  agv.position.copy(AGV_HOME);
  scene.add(agv);
  add(agv, rbox(1.2, 0.22, 1.0, 0.05), M.graphite, 0, 0.13, 0);
  add(agv, box(1.21, 0.035, 1.01), M.paint, 0, 0.19, 0);
  add(agv, cyl(0.05, 0.05, 0.06, 20), M.black, 0.52, 0.27, 0.42);
  const agvLed = add(agv, box(0.9, 0.018, 0.012), M.ledGreen, 0, 0.09, 0.506, false);
  const PALLET_TOP = 0.24 + 0.144;
  const pallet = new THREE.Group();
  pallet.position.y = 0.24;
  agv.add(pallet);
  for (let i = 0; i < 7; i++) add(pallet, box(1.2, 0.022, 0.1), M.wood, 0, 0.133, -0.45 + i * 0.15);
  for (const x of [-0.55, 0, 0.55]) {
    for (const z of [-0.45, 0, 0.45]) add(pallet, box(0.1, 0.078, 0.1), M.wood, x, 0.083, z);
    add(pallet, box(0.1, 0.022, 1.0), M.wood, x, 0.033, 0);
  }
  const slots = [];
  for (let layer = 0; layer < 2; layer++) {
    for (const [sx, sz] of [[-0.29, -0.23], [0.29, -0.23], [-0.29, 0.23], [0.29, 0.23]]) {
      slots.push(new THREE.Vector3(sx, PALLET_TOP + CH * layer + CH / 2, sz)); // carton centre, AGV frame
    }
  }
  const onPallet = [];

  /* ---------- reactor skid R-101 ---------- */
  const reactor = new THREE.Group();
  reactor.position.set(3.35, 0, -2.45);
  reactor.rotation.y = Math.PI; // nozzle and riser on the side facing the header
  scene.add(reactor);
  const profile = [
    [0, 0.66], [0.22, 0.68], [0.42, 0.74], [0.56, 0.83], [0.62, 0.95], [0.62, 2.15],
    [0.57, 2.26], [0.45, 2.33], [0.25, 2.37], [0, 2.38],
  ].map(([r, y]) => new THREE.Vector2(r, y));
  add(reactor, new THREE.LatheGeometry(profile, 64), M.steel);
  add(reactor, cyl(0.665, 0.665, 0.92, 64), M.jacket, 0, 1.4, 0);
  for (const y of [0.95, 1.86, 2.15]) add(reactor, new THREE.TorusGeometry(0.66, 0.018, 8, 64).rotateX(Math.PI / 2), M.steel, 0, y, 0);
  for (let i = 0; i < 4; i++) {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    add(reactor, cyl(0.04, 0.04, 1.05, 12), M.steel, Math.cos(a) * 0.6, 0.52, Math.sin(a) * 0.6);
    add(reactor, box(0.16, 0.02, 0.16), M.steel, Math.cos(a) * 0.6, 0.01, Math.sin(a) * 0.6);
  }
  add(reactor, cyl(0.17, 0.2, 0.26, 32), M.graphite, 0, 2.52, 0); // gearbox
  add(reactor, cyl(0.15, 0.15, 0.4, 32), M.graphite, 0, 2.85, 0); // agitator motor
  add(reactor, cyl(0.12, 0.12, 0.04, 32), M.alu, 0, 3.07, 0);
  for (const [x, z, r] of [[0.32, 0.12, 0.07], [-0.3, -0.2, 0.05], [0.05, -0.36, 0.06]]) {
    add(reactor, cyl(r, r, 0.18, 20), M.steel, x, 2.42, z);
    add(reactor, cyl(r + 0.03, r + 0.03, 0.03, 20), M.steel, x, 2.5, z);
  }
  add(reactor, cyl(0.16, 0.16, 0.08, 32), M.steel, -0.18, 2.38, 0.3); // manway
  add(reactor, cyl(0.05, 0.05, 0.3, 16), M.steel, 0, 0.53, 0); // bottom outlet
  add(reactor, rbox(0.12, 0.12, 0.1, 0.02), M.paint, 0.66, 1.6, 0.18); // temperature transmitter head
  // riser to the utility header
  const riser = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.32, 2.5, 0.12), new THREE.Vector3(0.32, 3.3, 0.12),
    new THREE.Vector3(0.36, 3.55, 0.5), new THREE.Vector3(0.4, 3.6, 0.77),
  ]); // in reactor space; ends on the header at world z -3.22
  add(reactor, new THREE.TubeGeometry(riser, 40, 0.05, 12, false), M.steel);
  add(reactor, rbox(0.16, 0.2, 0.16, 0.02), M.graphite, 0.32, 3.05, 0.12); // actuated valve
  add(reactor, cyl(0.07, 0.07, 0.18, 20), M.alu, 0.32, 3.22, 0.12);
  // utility header behind the cell
  for (const [y, z, r, mat] of [[3.6, -3.22, 0.07, M.steel], [3.38, -3.22, 0.09, M.alu]]) {
    add(scene, new THREE.CylinderGeometry(r, r, 7, 20).rotateZ(Math.PI / 2), mat, 1.9, y, z);
  }
  for (const x of [-1.2, 1.9, 5.0]) add(scene, box(0.14, 3.8, 0.14), M.graphite, x, 1.9, -3.4);

  /* ---------- control panel PLC-01 ---------- */
  const panel = new THREE.Group();
  panel.position.set(1.25, 0, -2.3);
  panel.rotation.y = -0.32;
  scene.add(panel);
  add(panel, box(1.24, 0.1, 0.52), M.black, 0, 0.05, 0);
  add(panel, rbox(1.2, 2.0, 0.5, 0.015), M.ral7035, 0, 1.1, 0);
  add(panel, box(1.24, 0.07, 0.54), M.paint, 0, 2.135, 0); // canopy in brand orange
  add(panel, box(0.008, 1.9, 0.01), M.graphite, 0, 1.1, 0.252);
  for (const x of [-0.07, 0.07]) add(panel, box(0.025, 0.16, 0.03), M.graphite, x, 1.15, 0.265);
  const hmi = canvasTexture(512, 336, () => {});
  hmi.texture.anisotropy = 4;
  add(panel, box(0.46, 0.32, 0.02), M.black, -0.3, 1.45, 0.255);
  const hmiScreen = add(panel, new THREE.PlaneGeometry(0.42, 0.276), new THREE.MeshBasicMaterial({ map: hmi.texture, toneMapped: false }), -0.3, 1.45, 0.2662, false);
  hmiScreen.castShadow = false;
  [M.ledGreen, M.ledAmberOff, M.ledRedOff].forEach((mat, i) => {
    add(panel, cylZ(0.022, 0.02, 16), mat, -0.42 + i * 0.09, 1.16, 0.258, false);
  });
  add(panel, box(0.2, 0.06, 0.006), new THREE.MeshStandardMaterial({ color: 0xf4f2ed, roughness: 0.6 }), 0.3, 1.82, 0.254, false);
  // stack light
  add(panel, cyl(0.02, 0.02, 0.12, 12), M.alu, 0.45, 2.23, 0.1);
  [M.ledRedOff, M.ledAmberOff, M.ledGreen].forEach((mat, i) => add(panel, cyl(0.045, 0.045, 0.07, 20), mat, 0.45, 2.53 - i * 0.075, 0.1, false));
  // edge gateway on the side wall, two antennas
  add(panel, rbox(0.06, 0.24, 0.18, 0.01), M.graphite, 0.63, 1.7, 0.05);
  add(panel, box(0.008, 0.03, 0.03), M.ledOrange, 0.662, 1.78, 0.1, false);
  for (const z of [-0.02, 0.12]) add(panel, cyl(0.008, 0.008, 0.22, 8), M.black, 0.63, 1.93, z);
  const edgeTop = new THREE.Object3D();
  edgeTop.position.set(0.63, 2.05, 0.05);
  panel.add(edgeTop);


  /* ---------- camera ---------- */
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 80);
  const lookAt = new THREE.Vector3(0.4, 1.0, -0.3);
  const view = { az: -0.42, el: 0.3, radius: 11 };

  const resize = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // the window is wide on desktop, nearly square on phones: back off as it narrows
    view.radius = 9.2 * THREE.MathUtils.clamp(1.7 / camera.aspect, 1, 1.6);
    lookAt.set(camera.aspect > 1.5 ? 1.05 : 1.0, 0.95, camera.aspect > 1.5 ? -0.35 : -0.4);
    camera.updateProjectionMatrix();
  };

  // the camera holds still: the cell's own work is the motion
  const placeCamera = () => {
    camera.position.set(
      lookAt.x + view.radius * Math.sin(view.az) * Math.cos(view.el),
      lookAt.y + view.radius * Math.sin(view.el),
      lookAt.z + view.radius * Math.cos(view.az) * Math.cos(view.el),
    );
    camera.lookAt(lookAt);
  };

  /* ---------- the cell's control logic ---------- */
  const HOME = new THREE.Vector3(0.95, 1.6, 1.0);
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const toCyl = (p) => ({ a: Math.atan2(p.x, p.z), r: Math.hypot(p.x, p.z), y: p.y });
  const cur = HOME.clone();
  let curYaw = 0;
  const queue = [];
  let step = null;
  let stepT = 0;
  let held = null;
  let cycle = { count: 0, last: 0, lastGrip: -1, time: 0 };
  let state = "Home";
  let dispatch = null;
  let simTime = 0;

  const moveTo = (to, dur, label) => queue.push({ kind: "move", to: to.clone(), dur, label });
  const wait = (dur) => queue.push({ kind: "wait", dur });
  const call = (fn) => queue.push({ kind: "call", fn });

  const tipWorld = new THREE.Vector3();
  const slotWorld = (k) => agv.localToWorld(slots[k].clone());

  const startCycle = () => {
    const k = onPallet.length;
    const pickTop = new THREE.Vector3(PICKX, CY + CH, CZ);
    const abovePick = pickTop.clone().add(new THREE.Vector3(0, 0.36, 0));
    const place = slotWorld(k).add(new THREE.Vector3(0, CH / 2, 0)); // carton top in the slot
    const abovePlace = place.clone().add(new THREE.Vector3(0, 0.4, 0));
    moveTo(abovePick, 1.0, "Approach");
    moveTo(pickTop, 0.5, "Pick");
    call(() => {
      held = belt.shift();
      held.state = "held";
      vacLed.material = M.ledGreen;
      if (cycle.lastGrip >= 0) cycle.last = simTime - cycle.lastGrip;
      cycle.lastGrip = simTime;
    });
    wait(0.22);
    moveTo(abovePick, 0.5, "Lift");
    moveTo(abovePlace, 1.35, "Transfer");
    moveTo(place, 0.55, "Place");
    call(() => {
      agv.attach(held.mesh);
      held.mesh.position.copy(slots[k]);
      held.mesh.rotation.set(0, 0, 0);
      held.state = "pallet";
      onPallet.push(held);
      held = null;
      vacLed.material = M.ledAmberOff;
      cycle.count += 1;
    });
    wait(0.18);
    moveTo(abovePlace, 0.45, "Retract");
    moveTo(HOME, 0.85, "Home");
    call(() => { if (onPallet.length >= slots.length) dispatch = { t: 0 }; });
  };

  const updateRobot = (dt) => {
    if (!step && queue.length) { step = queue.shift(); stepT = 0; if (step.kind === "move") { step.from = cur.clone(); step.fromYaw = curYaw; } }
    if (!step) {
      state = dispatch ? "Waiting for AGV" : "Home";
      const ready = belt.length && belt[0].x >= PICKX - 1e-3;
      if (!dispatch && ready && onPallet.length < slots.length) startCycle();
      return;
    }
    if (step.kind === "call") { step.fn(); step = null; return; }
    stepT += dt;
    const k = Math.min(stepT / step.dur, 1);
    if (step.kind === "move") {
      state = step.label;
      const e = easeInOut(k);
      const a = toCyl(step.from), b = toCyl(step.to);
      let da = b.a - a.a;
      da = Math.atan2(Math.sin(da), Math.cos(da)); // shortest way round
      const ang = a.a + da * e, rad = a.r + (b.r - a.r) * e;
      cur.set(Math.sin(ang) * rad, a.y + (b.y - a.y) * e, Math.cos(ang) * rad);
    }
    if (k >= 1) step = null;
  };

  const updateBelt = (dt) => {
    const v = 0.4;
    for (let i = 0; i < belt.length; i++) {
      const c = belt[i];
      const limit = i === 0 ? PICKX : belt[i - 1].x - GAP;
      c.x = Math.min(c.x + v * dt, limit);
      c.mesh.position.x = c.x;
    }
    const last = belt[belt.length - 1];
    if (belt.length < 5 && (!last || last.x > SPAWNX + GAP + 0.6)) spawn(SPAWNX);
    rollerAngle += (v * dt) / 0.034;
    const present = belt.length && belt[0].x >= PICKX - 1e-3;
    eyeLed.material = present ? M.ledGreen : M.ledAmberOff;
  };

  const updateAgv = (dt) => {
    if (!dispatch) return;
    dispatch.t += dt;
    const t = dispatch.t;
    const OUT = 10.5, outDur = 3.2, backDur = 2.8;
    if (t < outDur) {
      agv.position.x = AGV_HOME.x + (OUT - AGV_HOME.x) * easeInOut(t / outDur);
      agvLed.material = M.ledOrange;
    } else if (t < outDur + 0.4) {
      if (onPallet.length) {
        onPallet.forEach((c) => { c.mesh.visible = false; scene.attach(c.mesh); c.state = "free"; });
        onPallet.length = 0;
      }
    } else if (t < outDur + 0.4 + backDur) {
      agv.position.x = OUT + (AGV_HOME.x - OUT) * easeInOut((t - outDur - 0.4) / backDur);
    } else {
      agv.position.x = AGV_HOME.x;
      agvLed.material = M.ledGreen;
      dispatch = null;
      cycle.lastGrip = -1; // don't count the pallet change as a cycle
    }
  };

  /* ---------- HMI screen on PLC-01 ---------- */
  const tt = { v: 78.4, hist: Array.from({ length: 40 }, (_, i) => 78.3 + Math.sin(i / 4) * 0.25) };
  const drawHmi = () => {
    const { ctx } = hmi, w = 512, h = 336;
    ctx.fillStyle = "#0b0e15"; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#151a24"; ctx.fillRect(0, 0, w, 48);
    ctx.font = `500 22px ${MONO}`; ctx.textBaseline = "middle";
    ctx.fillStyle = "#eef0f5"; ctx.fillText("PLC-01  Block A", 18, 25);
    ctx.fillStyle = "#3ee089"; ctx.fillText("RUN", w - 62, 25);
    const rows = [
      ["TT-101", tt.v.toFixed(1), "°C"],
      ["PT-102", "4.20", "bar g"],
      ["ROB-01", `${onPallet.length} / 8`, "pallet"],
      ["CV-101", "0.40", "m/s"],
    ];
    rows.forEach(([tag, val, unit], i) => {
      const y = 82 + i * 40;
      ctx.font = `400 19px ${MONO}`; ctx.fillStyle = "#7a8296"; ctx.fillText(tag, 18, y);
      ctx.font = `500 26px ${MONO}`; ctx.fillStyle = "#eef0f5"; ctx.fillText(val, 140, y);
      ctx.font = `400 18px ${MONO}`; ctx.fillStyle = "#a3a9b8"; ctx.fillText(unit, 140 + ctx.measureText(val).width * 0.9 + 26, y);
    });
    // TT-101 trend
    const gx = 300, gy = 64, gw = 194, gh = 140;
    ctx.strokeStyle = "rgba(238,240,245,0.12)"; ctx.lineWidth = 1;
    ctx.strokeRect(gx, gy, gw, gh);
    ctx.setLineDash([5, 5]); ctx.beginPath();
    const sp = gy + gh * 0.3; ctx.moveTo(gx, sp); ctx.lineTo(gx + gw, sp); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeStyle = "#f48516"; ctx.lineWidth = 3; ctx.beginPath();
    tt.hist.forEach((v, i) => {
      const x = gx + (i / (tt.hist.length - 1)) * gw;
      const y = gy + gh - ((v - 77.4) / 2) * gh;
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.font = `400 16px ${MONO}`; ctx.fillStyle = "#7a8296"; ctx.fillText("TT-101 trend", gx, gy + gh + 22);
    ctx.fillStyle = "#151a24"; ctx.fillRect(0, h - 48, w, 48);
    ctx.font = `400 18px ${MONO}`; ctx.fillStyle = "#a3a9b8";
    ctx.fillText(`Step 6 of 9  Reaction hold   ROB-01 ${state}`, 18, h - 24);
    hmi.texture.needsUpdate = true;
  };

  /* ---------- callouts and telemetry ---------- */
  const callouts = calloutLayer ? Array.from(calloutLayer.querySelectorAll(".callout")) : [];
  const anchors = {
    rob: () => wrist.getWorldPosition(tmpA).add(up(0.3)),
    reactor: () => tmpA.set(reactor.position.x, 3.15, reactor.position.z),
    panel: () => panel.localToWorld(tmpA.set(-0.3, 2.2, 0.2)),
    edge: () => edgeTop.getWorldPosition(tmpA),
  };
  const tmpA = new THREE.Vector3();
  const upV = new THREE.Vector3();
  const up = (y) => upV.set(0, y, 0);
  const ndc = new THREE.Vector3();
  const live = {};
  document.querySelectorAll("[data-live]").forEach((el) => { live[el.dataset.live] = el; });
  const setLive = (k, v) => { if (live[k] && live[k].textContent !== v) live[k].textContent = v; };

  const updateCallouts = () => {
    if (!callouts.length) return;
    const cw = canvas.clientWidth, ch = canvas.clientHeight;
    const ox = 0, oy = 0;
    const shown = [];
    for (const el of callouts) {
      if (getComputedStyle(el).display === "none") continue;
      const p = anchors[el.dataset.anchor]();
      ndc.copy(p).project(camera);
      const x = ox + (ndc.x * 0.5 + 0.5) * cw;
      const y = oy + (-ndc.y * 0.5 + 0.5) * ch;
      const label = el.querySelector(".c-label");
      const lw = label.offsetWidth || 200, lh = label.offsetHeight || 44;
      const flip = x + lw > ox + cw - 16; // too close to the right edge: hang the label to the left
      const left = flip ? x - lw : x;
      const inView = ndc.z < 1 && left > ox + 8 && left + lw < ox + cw - 8 && y > oy + 72 && y < oy + ch - 24;
      const on = inView;
      el.classList.toggle("is-on", on);
      el.classList.toggle("is-flip", flip);
      el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
      if (on) shown.push({ el, x, y, lw, lh, flip, stem: 44 });
    }
    // keep labels from sitting on top of each other: lift the higher one
    shown.sort((a, b) => b.y - a.y);
    for (let i = 0; i < shown.length; i++) {
      const a = shown[i];
      for (let j = 0; j < i; j++) {
        const b = shown[j];
        const ax0 = a.flip ? a.x - a.lw : a.x, bx0 = b.flip ? b.x - b.lw : b.x;
        const aTop = a.y - a.stem - 4 - a.lh, bTop = b.y - b.stem - 4 - b.lh;
        const overlapX = ax0 < bx0 + b.lw + 8 && bx0 < ax0 + a.lw + 8;
        const overlapY = aTop < b.y - b.stem && bTop < a.y - a.stem;
        if (overlapX && overlapY) a.stem = Math.min(a.y - (bTop - 8) - 4, 200);
      }
      a.el.style.setProperty("--stem", `${Math.max(44, a.stem).toFixed(0)}px`);
      if (a.y - Math.max(44, a.stem) - 4 - a.lh < 8) a.el.classList.remove("is-on"); // would leave the window
    }
  };

  let uiClock = 0;
  const updateTelemetry = () => {
    const deg = (r) => THREE.MathUtils.radToDeg(r).toFixed(1) + "°";
    setLive("state", state);
    setLive("cycle", cycle.last ? cycle.last.toFixed(1) + " s" : "–");
    setLive("j1", deg(joints.t1));
    setLive("tt", tt.v.toFixed(1) + " °C");
    setLive("rob", `${state} · pallet ${onPallet.length} / 8`);
    setLive("reactor", `TT-101 ${tt.v.toFixed(1)} °C · PT-102 4.20 bar g`);
    setLive("panel", `Run · ${cycle.count} carton${cycle.count === 1 ? "" : "s"} palletised`);
    setLive("edge", `Uplink · ${cycle.last ? (3600 / cycle.last).toFixed(0) : "–"} cartons/h`);
  };

  /* ---------- frame ---------- */
  const simulate = (dt) => {
    simTime += dt;
    updateBelt(dt);
    updateRobot(dt);
    updateAgv(dt);
    solveIK(cur, curYaw);
    if (held) {
      tip.getWorldPosition(tipWorld);
      held.mesh.position.set(tipWorld.x, tipWorld.y - CH / 2, tipWorld.z);
      held.mesh.rotation.set(0, curYaw, 0);
    }
    tt.v += (78.4 - tt.v) * 0.02 + (Math.random() - 0.5) * 0.04 * dt * 30;
  };

  const timer = new THREE.Timer();
  timer.connect(document);
  let hmiClock = 0;
  const frame = () => {
    try { tick(); } catch (err) {
      console.error("Pretech 3D cell stopped:", err);
      renderer.setAnimationLoop(null);
    }
  };
  const tick = () => {
    timer.update();
    const dt = Math.min(timer.getDelta(), 1 / 20);
    simulate(dt);
    placeRollers();
    placeCamera();
    hmiClock += dt;
    if (hmiClock > 0.5) { hmiClock = 0; tt.hist.push(tt.v); tt.hist.shift(); drawHmi(); }
    renderer.render(scene, camera);
    updateCallouts();
    uiClock += dt;
    if (uiClock > 0.1) { uiClock = 0; updateTelemetry(); }
  };

  /* ---------- start ---------- */
  const renderStill = () => {
    placeCamera();
    renderer.render(scene, camera);
    updateCallouts();
    updateTelemetry();
  };

  // run only while the hero is on screen and the visitor hasn't paused it
  let running = false;
  let inView = true;
  let paused = false;

  resize();
  new ResizeObserver(() => { resize(); if (!running) renderStill(); }).observe(canvas);
  solveIK(cur, curYaw);
  drawHmi();

  placeCamera();
  try { await renderer.compileAsync(scene, camera); } catch (_) { /* compile on first render instead */ }
  renderer.render(scene, camera);
  canvas.classList.add("is-ready");
  if (calloutLayer) calloutLayer.classList.add("is-ready");

  const sync = () => {
    const on = inView && !paused;
    if (on === running) return;
    running = on;
    renderer.setAnimationLoop(on ? frame : null);
  };
  new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; sync(); }, { threshold: 0.02 }).observe(document.getElementById("twin") || hero);

  const pauseBtn = document.getElementById("cellPause");
  if (pauseBtn) {
    pauseBtn.hidden = false;
    pauseBtn.addEventListener("click", () => {
      paused = !paused;
      pauseBtn.setAttribute("aria-pressed", String(paused));
      pauseBtn.textContent = paused ? "Play" : "Pause";
      sync();
      if (paused) renderStill();
    });
  }
  sync();
})();
