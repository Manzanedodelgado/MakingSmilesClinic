/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
const N = Symbol("Comlink.proxy"), Q = Symbol("Comlink.endpoint"), Z = Symbol("Comlink.releaseProxy"), k = Symbol("Comlink.finalizer"), R = Symbol("Comlink.thrown"), v = (e) => typeof e == "object" && e !== null || typeof e == "function", m = {
  canHandle: (e) => v(e) && e[N],
  serialize(e) {
    const { port1: t, port2: n } = new MessageChannel();
    return U(e, t), [n, [n]];
  },
  deserialize(e) {
    return e.start(), ne(e);
  }
}, F = {
  canHandle: (e) => v(e) && R in e,
  serialize({ value: e }) {
    let t;
    return e instanceof Error ? t = {
      isError: !0,
      value: {
        message: e.message,
        name: e.name,
        stack: e.stack
      }
    } : t = { isError: !1, value: e }, [t, []];
  },
  deserialize(e) {
    throw e.isError ? Object.assign(new Error(e.value.message), e.value) : e.value;
  }
}, G = /* @__PURE__ */ new Map([
  ["proxy", m],
  ["throw", F]
]);
function ee(e, t) {
  for (const n of e)
    if (t === n || n === "*" || n instanceof RegExp && n.test(t))
      return !0;
  return !1;
}
function U(e, t = globalThis, n = ["*"]) {
  t.addEventListener("message", function r(s) {
    if (!s || !s.data)
      return;
    if (!ee(n, s.origin)) {
      console.warn(`Invalid origin '${s.origin}' for comlink proxy`);
      return;
    }
    const { id: o, type: a, path: f } = Object.assign({ path: [] }, s.data), l = (s.data.argumentList || []).map(S);
    let i;
    try {
      const c = f.slice(0, -1).reduce((d, w) => d[w], e), u = f.reduce((d, w) => d[w], e);
      switch (a) {
        case "GET":
          i = u;
          break;
        case "SET":
          c[f.slice(-1)[0]] = S(s.data.value), i = !0;
          break;
        case "APPLY":
          i = u.apply(c, l);
          break;
        case "CONSTRUCT":
          {
            const d = new u(...l);
            i = le(d);
          }
          break;
        case "ENDPOINT":
          {
            const { port1: d, port2: w } = new MessageChannel();
            U(e, w), i = ce(d, [d]);
          }
          break;
        case "RELEASE":
          i = void 0;
          break;
        default:
          return;
      }
    } catch (c) {
      i = { value: c, [R]: 0 };
    }
    Promise.resolve(i).catch((c) => ({ value: c, [R]: 0 })).then((c) => {
      const [u, d] = C(c);
      t.postMessage(Object.assign(Object.assign({}, u), { id: o }), d), a === "RELEASE" && (t.removeEventListener("message", r), V(t), k in e && typeof e[k] == "function" && e[k]());
    }).catch((c) => {
      const [u, d] = C({
        value: new TypeError("Unserializable return value"),
        [R]: 0
      });
      t.postMessage(Object.assign(Object.assign({}, u), { id: o }), d);
    });
  }), t.start && t.start();
}
function te(e) {
  return e.constructor.name === "MessagePort";
}
function V(e) {
  te(e) && e.close();
}
function ne(e, t) {
  const n = /* @__PURE__ */ new Map();
  return e.addEventListener("message", function(s) {
    const { data: o } = s;
    if (!o || !o.id)
      return;
    const a = n.get(o.id);
    if (a)
      try {
        a(o);
      } finally {
        n.delete(o.id);
      }
  }), B(e, n, [], t);
}
function D(e) {
  if (e)
    throw new Error("Proxy has been released and is not useable");
}
function H(e) {
  return E(e, /* @__PURE__ */ new Map(), {
    type: "RELEASE"
  }).then(() => {
    V(e);
  });
}
const T = /* @__PURE__ */ new WeakMap(), O = "FinalizationRegistry" in globalThis && new FinalizationRegistry((e) => {
  const t = (T.get(e) || 0) - 1;
  T.set(e, t), t === 0 && H(e);
});
function re(e, t) {
  const n = (T.get(t) || 0) + 1;
  T.set(t, n), O && O.register(e, t, e);
}
function se(e) {
  O && O.unregister(e);
}
function B(e, t, n = [], r = function() {
}) {
  let s = !1;
  const o = new Proxy(r, {
    get(a, f) {
      if (D(s), f === Z)
        return () => {
          se(o), H(e), t.clear(), s = !0;
        };
      if (f === "then") {
        if (n.length === 0)
          return { then: () => o };
        const l = E(e, t, {
          type: "GET",
          path: n.map((i) => i.toString())
        }).then(S);
        return l.then.bind(l);
      }
      return B(e, t, [...n, f]);
    },
    set(a, f, l) {
      D(s);
      const [i, c] = C(l);
      return E(e, t, {
        type: "SET",
        path: [...n, f].map((u) => u.toString()),
        value: i
      }, c).then(S);
    },
    apply(a, f, l) {
      D(s);
      const i = n[n.length - 1];
      if (i === Q)
        return E(e, t, {
          type: "ENDPOINT"
        }).then(S);
      if (i === "bind")
        return B(e, t, n.slice(0, -1));
      const [c, u] = J(l);
      return E(e, t, {
        type: "APPLY",
        path: n.map((d) => d.toString()),
        argumentList: c
      }, u).then(S);
    },
    construct(a, f) {
      D(s);
      const [l, i] = J(f);
      return E(e, t, {
        type: "CONSTRUCT",
        path: n.map((c) => c.toString()),
        argumentList: l
      }, i).then(S);
    }
  });
  return re(o, e), o;
}
function oe(e) {
  return Array.prototype.concat.apply([], e);
}
function J(e) {
  const t = e.map(C);
  return [t.map((n) => n[0]), oe(t.map((n) => n[1]))];
}
const Y = /* @__PURE__ */ new WeakMap();
function ce(e, t) {
  return Y.set(e, t), e;
}
function le(e) {
  return Object.assign(e, { [N]: !0 });
}
function C(e) {
  for (const [t, n] of G)
    if (n.canHandle(e)) {
      const [r, s] = n.serialize(e);
      return [
        {
          type: "HANDLER",
          name: t,
          value: r
        },
        s
      ];
    }
  return [
    {
      type: "RAW",
      value: e
    },
    Y.get(e) || []
  ];
}
function S(e) {
  switch (e.type) {
    case "HANDLER":
      return G.get(e.name).deserialize(e.value);
    case "RAW":
      return e.value;
  }
}
function E(e, t, n, r) {
  return new Promise((s) => {
    const o = ae();
    t.set(o, s), e.start && e.start(), e.postMessage(Object.assign({ id: o }, n), r);
  });
}
function ae() {
  return new Array(4).fill(0).map(() => Math.floor(Math.random() * Number.MAX_SAFE_INTEGER).toString(16)).join("-");
}
async function fe(e, t) {
  let n = t.buffer, r = t.byteOffset;
  const s = t.length;
  return e.bitsAllocated === 16 ? (r % 2 && (n = n.slice(r), r = 0), e.pixelRepresentation === 0 ? e.pixelData = new Uint16Array(n, r, s / 2) : e.pixelData = new Int16Array(n, r, s / 2)) : e.bitsAllocated === 8 || e.bitsAllocated === 1 ? e.pixelData = t : e.bitsAllocated === 32 && (r % 2 && (n = n.slice(r), r = 0), e.pixelData = new Float32Array(n, r, s / 4)), e;
}
function ie(e) {
  return (e & 255) << 8 | e >> 8 & 255;
}
async function ue(e, t) {
  if (e.bitsAllocated === 16) {
    let n = t.buffer, r = t.byteOffset;
    const s = t.length;
    r % 2 && (n = n.slice(r), r = 0), e.pixelRepresentation === 0 ? e.pixelData = new Uint16Array(n, r, s / 2) : e.pixelData = new Int16Array(n, r, s / 2);
    for (let o = 0; o < e.pixelData.length; o++)
      e.pixelData[o] = ie(e.pixelData[o]);
  } else e.bitsAllocated === 8 && (e.pixelData = t);
  return e;
}
async function de(e, t) {
  if (e.bitsAllocated === 8)
    return e.planarConfiguration ? we(e, t) : ye(e, t);
  if (e.bitsAllocated === 16)
    return pe(e, t);
  throw new Error("unsupported pixel format for RLE");
}
function ye(e, t) {
  const n = t, r = e.rows * e.columns, s = new ArrayBuffer(r * e.samplesPerPixel), o = new DataView(n.buffer, n.byteOffset), a = new Int8Array(n.buffer, n.byteOffset), f = new Int8Array(s);
  let l = 0;
  const i = o.getInt32(0, !0);
  for (let c = 0; c < i; ++c) {
    l = c;
    let u = o.getInt32((c + 1) * 4, !0), d = o.getInt32((c + 2) * 4, !0);
    d === 0 && (d = n.length);
    const w = r * i;
    for (; u < d; ) {
      const y = a[u++];
      if (y >= 0 && y <= 127)
        for (let p = 0; p < y + 1 && l < w; ++p)
          f[l] = a[u++], l += e.samplesPerPixel;
      else if (y <= -1 && y >= -127) {
        const p = a[u++];
        for (let h = 0; h < -y + 1 && l < w; ++h)
          f[l] = p, l += e.samplesPerPixel;
      }
    }
  }
  return e.pixelData = new Uint8Array(s), e;
}
function we(e, t) {
  const n = t, r = e.rows * e.columns, s = new ArrayBuffer(r * e.samplesPerPixel), o = new DataView(n.buffer, n.byteOffset), a = new Int8Array(n.buffer, n.byteOffset), f = new Int8Array(s);
  let l = 0;
  const i = o.getInt32(0, !0);
  for (let c = 0; c < i; ++c) {
    l = c * r;
    let u = o.getInt32((c + 1) * 4, !0), d = o.getInt32((c + 2) * 4, !0);
    d === 0 && (d = n.length);
    const w = r * i;
    for (; u < d; ) {
      const y = a[u++];
      if (y >= 0 && y <= 127)
        for (let p = 0; p < y + 1 && l < w; ++p)
          f[l] = a[u++], l++;
      else if (y <= -1 && y >= -127) {
        const p = a[u++];
        for (let h = 0; h < -y + 1 && l < w; ++h)
          f[l] = p, l++;
      }
    }
  }
  return e.pixelData = new Uint8Array(s), e;
}
function pe(e, t) {
  const n = t, r = e.rows * e.columns, s = new ArrayBuffer(r * e.samplesPerPixel * 2), o = new DataView(n.buffer, n.byteOffset), a = new Int8Array(n.buffer, n.byteOffset), f = new Int8Array(s), l = o.getInt32(0, !0);
  for (let i = 0; i < l; ++i) {
    let c = 0;
    const u = i === 0 ? 1 : 0;
    let d = o.getInt32((i + 1) * 4, !0), w = o.getInt32((i + 2) * 4, !0);
    for (w === 0 && (w = n.length); d < w; ) {
      const y = a[d++];
      if (y >= 0 && y <= 127)
        for (let p = 0; p < y + 1 && c < r; ++p)
          f[c * 2 + u] = a[d++], c++;
      else if (y <= -1 && y >= -127) {
        const p = a[d++];
        for (let h = 0; h < -y + 1 && c < r; ++h)
          f[c * 2 + u] = p, c++;
      }
    }
  }
  return e.pixelRepresentation === 0 ? e.pixelData = new Uint16Array(s) : e.pixelData = new Int16Array(s), e;
}
const I = {
  JpegImage: void 0,
  decodeConfig: {}
};
function be(e) {
  return I.decodeConfig = e, I.JpegImage ? Promise.resolve() : new Promise((t, n) => {
    import("./jpeg-VemIX8A4.js").then((r) => {
      I.JpegImage = r.default, t();
    }).catch(n);
  });
}
async function xe(e, t) {
  if (await be(), typeof I.JpegImage > "u")
    throw new Error("No JPEG Baseline decoder loaded");
  const n = new I.JpegImage();
  if (n.parse(t), n.colorTransform = !1, e.bitsAllocated === 8)
    return e.pixelData = n.getData(e.columns, e.rows), e;
  if (e.bitsAllocated === 16)
    return e.pixelData = n.getData16(e.columns, e.rows), e;
}
const g = {
  jpeg: void 0,
  decodeConfig: {}
};
function he(e) {
  return g.decodeConfig = e, g.jpeg ? Promise.resolve() : new Promise((t, n) => {
    import("./lossless-CuUeugdm.js").then(({ Decoder: r }) => {
      const s = new r();
      g.jpeg = s, t();
    }, n);
  });
}
async function Ae(e, t) {
  if (await he(), typeof g.jpeg > "u")
    throw new Error("No JPEG Lossless decoder loaded");
  const n = e.bitsAllocated <= 8 ? 1 : 2, r = t.buffer, s = g.jpeg.decode(r, t.byteOffset, t.length, n);
  return e.pixelRepresentation === 0 ? e.bitsAllocated === 16 ? (e.pixelData = new Uint16Array(s.buffer), e) : (e.pixelData = new Uint8Array(s.buffer), e) : (e.pixelData = new Int16Array(s.buffer), e);
}
function Pe(e, t) {
  const { rows: n, columns: r, data: s } = e, { rows: o, columns: a, data: f } = t, l = [], i = [], c = [];
  for (let u = 0; u < a; u++) {
    const d = u * (r - 1) / (a - 1);
    l[u] = Math.floor(d), i[u] = Math.min(l[u] + 1, r - 1), c[u] = d - l[u];
  }
  for (let u = 0; u < o; u++) {
    const d = u * (n - 1) / (o - 1), w = Math.floor(d) * r, y = Math.min(w + r, (n - 1) * r), p = d - Math.floor(d), h = 1 - p, x = u * a;
    for (let b = 0; b < a; b++) {
      const A = s[w + l[b]], P = s[w + i[b]], K = s[y + l[b]], X = s[y + i[b]], j = 1 - c[b];
      f[x + b] = (A * j + P * c[b]) * h + (K * j + X * c[b]) * p;
    }
  }
  return f;
}
function Se(e, t) {
  const { rows: n, columns: r, pixelData: s, samplesPerPixel: o = 1 } = e, { rows: a, columns: f, pixelData: l } = t, i = [];
  for (let c = 0; c < f; c++) {
    const u = c * (r - 1) / (f - 1);
    i[c] = Math.floor(u) * o;
  }
  for (let c = 0; c < a; c++) {
    const u = c * (n - 1) / (a - 1), d = Math.floor(u) * r * o, w = c * f;
    for (let y = 0; y < f; y++)
      for (let p = 0; p < o; p++)
        l[w + y + p] = s[d + i[y] + p];
  }
  return l;
}
function Ee(e, t) {
  const n = e.length, { rescaleSlope: r, rescaleIntercept: s, suvbw: o } = t;
  if (t.modality === "PT" && typeof o == "number" && !isNaN(o))
    for (let a = 0; a < n; a++)
      e[a] = o * (e[a] * r + s);
  else
    for (let a = 0; a < n; a++)
      e[a] = e[a] * r + s;
  return !0;
}
function Ie(e) {
  let t = e[0], n = e[0], r;
  const s = e.length;
  for (let o = 1; o < s; o++)
    r = e[o], t = Math.min(t, r), n = Math.max(n, r);
  return {
    min: t,
    max: n
  };
}
function W(e, t) {
  let n;
  return Number.isInteger(e) && Number.isInteger(t) && (e >= 0 ? t <= 255 ? n = Uint8Array : t <= 65535 && (n = Uint16Array) : e >= -128 && t <= 127 ? n = Int8Array : e >= -32768 && t <= 32767 && (n = Int16Array)), n || Float32Array;
}
function ge(e, t, n) {
  return W(e, t) === n;
}
function De(e) {
  return e === "RGB" || e === "PALETTE COLOR" || e === "YBR_FULL" || e === "YBR_FULL_422" || e === "YBR_PARTIAL_422" || e === "YBR_PARTIAL_420" || e === "YBR_RCT" || e === "YBR_ICT";
}
let L, M, z, _;
async function Re() {
  return L || (L = (await import("./decodeJPEGBaseline8Bit-C6k2NQny.js")).default), L;
}
async function Te() {
  return M || (M = (await import("./decodeJPEGLS-CGIdpbVm.js")).default), M;
}
async function Oe() {
  return z || (z = (await import("./decodeJPEG2000-D32V7CK9.js")).default), z;
}
async function Ce() {
  return _ || (_ = (await import("./decodeHTJ2K-CHrehG6M.js")).default), _;
}
const ke = { bilinear: Pe, replicate: Se }, $ = {
  Uint8Array,
  Uint16Array,
  Int16Array,
  Float32Array
};
function Le(e, t, n, r) {
  const s = e.pixelRepresentation !== void 0 && e.pixelRepresentation === 1, o = s && e.bitsStored !== void 0 ? 32 - e.bitsStored : void 0;
  if (s && o !== void 0)
    for (let x = 0; x < e.pixelData.length; x++)
      e.pixelData[x] = e.pixelData[x] << o >> o;
  let a = e.pixelData;
  e.pixelDataLength = e.pixelData.length;
  const { min: f, max: l } = Ie(e.pixelData), i = typeof t.allowFloatRendering < "u" ? t.allowFloatRendering : !0;
  let c = De(e.photometricInterpretation) && t.targetBuffer?.offset === void 0;
  const d = t.preScale?.enabled && Object.values(t.preScale.scalingParameters || {}).some(
    (x) => typeof x == "number" && !Number.isInteger(x)
  ), w = !t.preScale?.enabled || !i && d, y = t.targetBuffer?.type;
  if (y && t.preScale?.enabled && !w) {
    const { rescaleSlope: x, rescaleIntercept: b } = t.preScale.scalingParameters, A = x * f + b, P = x * l + b;
    c = !ge(A, P, $[y]);
  }
  y && !c ? a = Me(t, e) : t.preScale?.enabled && !w ? a = ze(t, f, l, e) : a = q(f, l, e);
  let p = f, h = l;
  if (t.preScale?.enabled && !w) {
    const x = t.preScale.scalingParameters;
    if (!x)
      throw new Error("scalingParameters must be defined if preScale.enabled is true");
    const { rescaleSlope: b, rescaleIntercept: A, suvbw: P } = x;
    typeof b == "number" && typeof A == "number" && (Ee(a, x), e.preScale = { ...t.preScale, scaled: !0 }, p = b * f + A, h = b * l + A, P && (p *= P, h *= P));
  } else w && (e.preScale = { enabled: !0, scaled: !1 });
  return e.pixelData = a, e.smallestPixelValue = p, e.largestPixelValue = h, e.decodeTimeInMS = (/* @__PURE__ */ new Date()).getTime() - n, e;
}
function Me(e, t, n) {
  const { arrayBuffer: r, type: s, offset: o = 0, length: a, rows: f } = e.targetBuffer, l = $[s];
  if (!l) throw new Error(`target array ${s} is not supported`);
  f && f !== t.rows && Be(t, e.targetBuffer, l);
  const i = a ?? t.pixelDataLength - o;
  if (i !== t.pixelData.length)
    throw new Error("target array length mismatch");
  const c = r ? new l(r, o, i) : new l(i);
  return c.set(t.pixelData, 0), c;
}
function ze(e, t, n, r) {
  const s = e.preScale.scalingParameters;
  if (!s) throw new Error("scalingParameters required");
  const { rescaleSlope: o, rescaleIntercept: a } = s;
  let f = t, l = n;
  return typeof o == "number" && typeof a == "number" && (f = o * t + a, l = o * n + a), q(f, l, r);
}
function q(e, t, n) {
  const r = W(e, t), s = new r(n.pixelData.length);
  return s.set(n.pixelData, 0), s;
}
function _e(e, t, n) {
  const r = t.rows * t.columns * e.samplesPerPixel, s = new n(r);
  return {
    pixelData: s,
    rows: t.rows,
    columns: t.columns,
    frameInfo: { ...e.frameInfo, rows: t.rows, columns: t.columns },
    imageInfo: {
      ...e.imageInfo,
      rows: t.rows,
      columns: t.columns,
      bytesPerPixel: s.byteLength / r
    }
  };
}
function Be(e, t, n) {
  const r = _e(e, t, n), s = t.scalingType || "replicate";
  return ke[s](e, r), Object.assign(e, r), e.pixelDataLength = e.pixelData.length, e;
}
async function Ue(e, t, n, r, s, o) {
  const a = (/* @__PURE__ */ new Date()).getTime();
  let f = null;
  switch (t) {
    case "1.2.840.10008.1.2":
    case "1.2.840.10008.1.2.1":
    case "1.2.840.10008.1.2.1.99":
      f = fe(e, n);
      break;
    case "1.2.840.10008.1.2.2":
      f = ue(e, n);
      break;
    case "1.2.840.10008.1.2.5":
      f = de(e, n);
      break;
    case "1.2.840.10008.1.2.4.50": {
      f = (await Re())(n, { ...e });
      break;
    }
    case "1.2.840.10008.1.2.4.51":
      f = xe(e, n);
      break;
    case "1.2.840.10008.1.2.4.57":
    case "1.2.840.10008.1.2.4.70":
      f = Ae(e, n);
      break;
    case "1.2.840.10008.1.2.4.80":
    case "1.2.840.10008.1.2.4.81": {
      f = (await Te())(n, {
        signed: e.pixelRepresentation === 1,
        bytesPerPixel: e.bitsAllocated <= 8 ? 1 : 2,
        ...e
      });
      break;
    }
    case "1.2.840.10008.1.2.4.90":
    case "1.2.840.10008.1.2.4.91": {
      f = (await Oe())(n, { ...e });
      break;
    }
    case "3.2.840.10008.1.2.4.96":
    case "1.2.840.10008.1.2.4.201":
    case "1.2.840.10008.1.2.4.202":
    case "1.2.840.10008.1.2.4.203": {
      f = (await Ce())(n, { ...e });
      break;
    }
    default:
      throw new Error(`no decoder for transfer syntax ${t}`);
  }
  if (!f) throw new Error("decodePromise not defined");
  const l = await f, i = Le(l, s, a);
  return o?.(i), i;
}
const je = {
  decodeTask({
    imageFrame: e,
    transferSyntax: t,
    decodeConfig: n,
    options: r,
    pixelData: s,
    callbackFn: o
  }) {
    return Ue(e, t, s, n, r, o);
  }
};
U(je);
//# sourceMappingURL=decodeImageFrameWorker-AH7Pp-7b.js.map
