/* Sfondo "PatternWaves" (preset silk) in WebGL puro, senza dipendenze.
   Parametri equivalenti a: color #3B82F6, backgroundColor #000000, fade "edges",
   interactive, cursorSize 50, cursorStrength 0.6. Ferma con "riduci movimento"
   (un solo fotogramma) e in pausa quando la scheda non è visibile. */
(function () {
  "use strict";
  var cfg = window.LUMEN_WELCOME || {};
  var OPTIONS = { color: "#3B82F6", backgroundColor: "#000000", fade: "edges", interactive: true,
    cursorSize: 50, cursorStrength: 0.6, speed: 0.35, scale: 1.0 };

  // --- testi e collegamenti dalla configurazione del container ---------------------------
  function safeUrl(u) { return typeof u === "string" && /^https?:\/\/[^\s"'<>]+$/i.test(u) ? u : ""; }
  var name = typeof cfg.centerName === "string" && cfg.centerName.trim() ? cfg.centerName.trim() : "";
  if (name) {
    document.querySelectorAll("[data-center-name]").forEach(function (el) { el.textContent = name; });
    document.title = "Videolezioni · " + name;
  }
  var site = safeUrl(cfg.siteUrl), app = safeUrl(cfg.appUrl);
  var siteLink = document.querySelector("[data-site-link]");
  var appLink = document.querySelector("[data-app-link]");
  if (site) siteLink.href = site; else if (app) { siteLink.href = app; }
  if (app && site && app !== site) { appLink.href = app; appLink.hidden = false; }

  // --- sfondo -----------------------------------------------------------------------------
  var canvas = document.getElementById("waves");
  var gl = canvas.getContext("webgl", { antialias: false, alpha: false, premultipliedAlpha: false });
  if (!gl) return; // resta il gradiente CSS di ripiego

  function hex(c) { var n = parseInt(c.slice(1), 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; }

  var vs = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
  var fs = [
    "precision highp float;",
    "uniform vec2 uRes;uniform float uTime;uniform vec3 uColor;uniform vec3 uBg;",
    "uniform vec2 uMouse;uniform float uMouseOn;uniform float uRadius;uniform float uStrength;uniform float uFade;",
    "float hash(vec2 p){return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453);}",
    "void main(){",
    "  vec2 frag=gl_FragCoord.xy;",
    "  vec2 uv=frag/uRes;",
    "  float aspect=uRes.x/uRes.y;",
    "  vec2 tex=vec2(uv.x*aspect,uv.y)*1.6;",
    // cursore: spinta radiale morbida attorno al puntatore
    "  vec2 d=frag-uMouse;float dist=length(d);",
    "  float infl=uMouseOn*exp(-(dist*dist)/(2.*uRadius*uRadius));",
    "  tex+= (dist>0.001? d/dist : vec2(0.)) * infl * uStrength * 0.18;",
    "  float t=uTime;",
    // silk: pieghe sinusoidali intrecciate
    "  tex.y+=0.035*sin(8.*tex.x-t*1.2);",
    "  float pat=0.6+0.4*sin(5.*(tex.x+tex.y+cos(3.*tex.x+5.*tex.y)+0.02*t)+sin(20.*(tex.x+tex.y-0.1*t)));",
    "  float silk=pow(clamp(pat,0.,1.),2.2);",
    "  float glow=infl*0.35;",
    "  vec3 col=mix(uBg,uColor,clamp(silk*0.95+glow,0.,1.));",
    // fade ai bordi
    "  vec2 e=smoothstep(vec2(0.),vec2(0.28),uv)*smoothstep(vec2(0.),vec2(0.28),1.-uv);",
    "  float edge=mix(1.,e.x*e.y,uFade);",
    "  col=mix(uBg,col,edge);",
    "  col-= (hash(frag+t)-0.5)/90.;", // grana leggera, niente bande
    "  gl_FragColor=vec4(col,1.);",
    "}"
  ].join("\n");

  function shader(type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  var prog;
  try {
    prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("link");
  } catch (e) { return; }
  gl.useProgram(prog);
  var buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var loc = gl.getAttribLocation(prog, "p");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  var U = {};
  ["uRes", "uTime", "uColor", "uBg", "uMouse", "uMouseOn", "uRadius", "uStrength", "uFade"].forEach(function (k) { U[k] = gl.getUniformLocation(prog, k); });
  gl.uniform3fv(U.uColor, hex(OPTIONS.color));
  gl.uniform3fv(U.uBg, hex(OPTIONS.backgroundColor));
  gl.uniform1f(U.uStrength, OPTIONS.cursorStrength);
  gl.uniform1f(U.uFade, OPTIONS.fade === "edges" ? 1 : 0);

  var dpr = 1, W = 0, H = 0;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5); // nitido ma leggero
    W = Math.floor(canvas.clientWidth * dpr); H = Math.floor(canvas.clientHeight * dpr);
    canvas.width = W; canvas.height = H;
    gl.viewport(0, 0, W, H);
    gl.uniform2f(U.uRes, W, H);
    gl.uniform1f(U.uRadius, OPTIONS.cursorSize * 2.2 * dpr);
  }
  resize();
  window.addEventListener("resize", resize);

  // puntatore con inerzia (molla), si spegne dolcemente quando esce
  var target = { x: -9999, y: -9999, on: 0 }, cur = { x: -9999, y: -9999, on: 0 };
  if (OPTIONS.interactive) {
    window.addEventListener("pointermove", function (ev) {
      target.x = ev.clientX * dpr; target.y = H - ev.clientY * dpr; target.on = 1;
      if (cur.x < -9000) { cur.x = target.x; cur.y = target.y; }
    }, { passive: true });
    document.addEventListener("pointerleave", function () { target.on = 0; });
    window.addEventListener("blur", function () { target.on = 0; });
  }

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var start = performance.now(), raf = 0;
  function frame(now) {
    var t = (now - start) / 1000 * OPTIONS.speed * 2.0;
    cur.x += (target.x - cur.x) * 0.12; cur.y += (target.y - cur.y) * 0.12; cur.on += (target.on - cur.on) * 0.08;
    gl.uniform1f(U.uTime, t);
    gl.uniform2f(U.uMouse, cur.x, cur.y);
    gl.uniform1f(U.uMouseOn, cur.on);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!reduce.matches) raf = requestAnimationFrame(frame);
  }
  function play() { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
  document.addEventListener("visibilitychange", function () { if (document.hidden) cancelAnimationFrame(raf); else play(); });
  if (reduce.addEventListener) reduce.addEventListener("change", play);
  play();
})();
