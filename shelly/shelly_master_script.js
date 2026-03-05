/**
 * Shelly Plus Uni Master Script (Zulauf-Geraet)
 * - Liest Zulauf lokal (input:2)
 * - Liest Ablauf remote (zweiter Shelly)
 * - Berechnet Trinkwasser = Zulauf - Ablauf
 * - Fuehrt Tages-/Wochen-/Monatswerte (ohne Counter-Reset)
 * - Sendet taeglich WhatsApp Report ueber WAHA
 *
 * Hinweis:
 * - xcounts auf BEIDEN Shellys auf x/1380 setzen (FL-S402B: F=23*Q(L/min)).
 * - Keine echten Virtual Components auf Plus Uni: Wert ist Script-intern.
 */

let CFG = {
  inputId: 2,
  remoteAblaufStatusUrl: "http://SHELLY_ABWASSER_IP/rpc/Input.GetStatus?id=2",
  remotePlugStatusUrl: "http://SHELLY_PLUG_IP/rpc/Shelly.GetStatus",
  tickSeconds: 1800,
  dailySendHour: 6,
  sendTestOnStart: false, // true => sendet beim Script-Start sofort einen Testreport
  sendDailyReportTestOnStart: false, // true => sendet einmal Chart + Tagesbericht (wie morgens) zum Testen
  remoteOfflineFailThreshold: 2, // ab wie vielen Fehlern "offline" gesetzt wird

  // WAHA
  wahaUrl: "https://your-waha.example.com/api/sendText",
  wahaApiKey: "CHANGE_ME",
  waChatId: "CHANGE_ME@g.us",
  waSession: "default",
  waRetries: 3,
  waRetryBaseSec: 2,
};

let state = {
  // totals in liters
  inTotal: 0,
  outTotal: 0,
  drinkTotal: 0,

  // anchors
  dayKey: "",
  dayInStart: 0,
  dayOutStart: 0,
  weekKey: "",
  weekInStart: 0,
  weekOutStart: 0,
  monthKey: "",
  monthInStart: 0,
  monthOutStart: 0,

  // rollover snapshot
  yIn: 0,
  yOut: 0,
  yDrink: 0,
  yKey: "",
  lwIn: 0,
  lwOut: 0,
  lwDrink: 0,
  lwKey: "",
  lmIn: 0,
  lmOut: 0,
  lmDrink: 0,
  lmKey: "",

  // last known totals
  lastIn: 0,
  lastOut: 0,

  // report de-duplication
  lastReportDay: "",
  remoteFailCount: 0,
  remoteOffline: false,

  // Plug Energie (kWh)
  energyTotal: 0,
  lastEnergy: 0,
  dayEnergyStart: 0,
  weekEnergyStart: 0,
  monthEnergyStart: 0,
  yEnergy: 0,
  lwEnergy: 0,
  lmEnergy: 0,
  plugFailCount: 0,
  plugOffline: false,

  // 30-Min-Slots Produktwasser deltas (integers, 1/10 Liter), 48 Slots/Tag
  todayHourly: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  yHourly:     [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],

  // 30-Min-Slots Energie deltas (integers, 0.01 kWh), 48 Slots/Tag
  todayEnergySlots: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  yEnergySlots:     [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],

  initialized: false,
};

let busy = false;

function z(n) {
  return n < 10 ? "0" + n : "" + n;
}

function round3(v) {
  return Math.round(v * 1000) / 1000;
}

function zero48Array() {
  let a = [];
  let i = 0;
  while (i < 48) {
    a.push(0);
    i++;
  }
  return a;
}

function asLitersFromStatus(st) {
  if (!st || !st.counts) return 0;
  if (typeof st.counts.xtotal === "number") return st.counts.xtotal;
  if (typeof st.counts.total === "number") return st.counts.total / 1380.0;
  return 0;
}

function safeLitersFromStatus(st, sourceLabel) {
  try {
    return asLitersFromStatus(st);
  } catch (e) {
    print("parse liters error (" + sourceLabel + ")");
    return 0;
  }
}

function asEnergyKwhFromStatus(st) {
  if (!st) return 0;

  // Gen2 Plug: Shelly.GetStatus -> switch:0.aenergy.total (Wh)
  let sw = st["switch:0"];
  if (sw && sw.aenergy && typeof sw.aenergy.total === "number") {
    return sw.aenergy.total / 1000.0;
  }

  // Weitere Gen2 Komponenten mit Energie
  let em = st["em:0"];
  if (em && em.aenergy && typeof em.aenergy.total === "number") {
    return em.aenergy.total / 1000.0;
  }

  // Gen1 Muster
  if (st.meters && st.meters[0] && typeof st.meters[0].total === "number") {
    return st.meters[0].total / 1000.0;
  }
  if (st.emeters && st.emeters[0] && typeof st.emeters[0].total === "number") {
    return st.emeters[0].total / 1000.0;
  }

  // Fallback
  if (typeof st.total_act_energy === "number") return st.total_act_energy / 1000.0;
  if (typeof st.total === "number") return st.total / 1000.0;
  return 0;
}

function safeEnergyKwhFromStatus(st, sourceLabel) {
  try {
    return asEnergyKwhFromStatus(st);
  } catch (e) {
    print("parse energy error (" + sourceLabel + ")");
    return 0;
  }
}

function dayKeyNow(d) {
  return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate());
}

function monthKeyNow(d) {
  return d.getFullYear() + "-" + z(d.getMonth() + 1);
}

function isLeapYear(y) {
  if (y % 4 !== 0) return false;
  if (y % 100 !== 0) return true;
  return y % 400 === 0;
}

function dayOfYear(d) {
  let mdays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let y = d.getFullYear();
  if (isLeapYear(y)) mdays[1] = 29;
  let m = d.getMonth();
  let sum = 0;
  let i = 0;
  while (i < m) {
    sum += mdays[i];
    i++;
  }
  return sum + d.getDate();
}

// ISO week key: YYYY-Www (ohne Date-Setter, kompatibel mit Shelly mJS)
function weekKeyNow(d) {
  let y = d.getFullYear();
  let doy = dayOfYear(d);
  let isoWeekday = ((d.getDay() + 6) % 7) + 1; // Mon=1..Sun=7
  let week = Math.floor((doy - isoWeekday + 10) / 7);

  function weeksInIsoYear(year) {
    let jan1 = new Date(year, 0, 1);
    let jan1Iso = ((jan1.getDay() + 6) % 7) + 1;
    if (jan1Iso === 4) return 53; // Donnerstag
    if (jan1Iso === 3 && isLeapYear(year)) return 53; // Schaltjahr + Mittwoch
    return 52;
  }

  if (week < 1) {
    y = y - 1;
    week = weeksInIsoYear(y);
  } else {
    let maxWeek = weeksInIsoYear(y);
    if (week > maxWeek) {
      y = y + 1;
      week = 1;
    }
  }

  return y + "-W" + z(week);
}

function todayHm(d) {
  return z(d.getHours()) + ":" + z(d.getMinutes());
}

function clampDrink(inL, outL) {
  let v = inL - outL;
  return v < 0 ? 0 : v;
}

function fmtL(v) {
  return round3(v) + " L";
}

function fmtPct(v) {
  return round3(v) + " %";
}

function fmtFixed(v, decimals) {
  let m = 1;
  let i = 0;
  while (i < decimals) {
    m *= 10;
    i++;
  }
  let n = Math.round(v * m) / m;
  let s = "" + n;
  let dot = s.indexOf(".");
  if (dot < 0) {
    s += ".";
    dot = s.length - 1;
  }
  let fracLen = s.length - dot - 1;
  while (fracLen < decimals) {
    s += "0";
    fracLen++;
  }
  return s;
}

function fmtL2(v) {
  return fmtFixed(v, 2) + " L";
}

function fmtPct2(v) {
  return fmtFixed(v, 2) + " %";
}

function fmtKwh2(v) {
  return fmtFixed(v, 2) + " kWh";
}

function padRight(text, width) {
  let s = text;
  while (s.length < width) s += " ";
  return s;
}

function tableRow(label, value) {
  return padRight(label, 14) + value;
}

function kvsSet(key, value, cb) {
  Shelly.call("KVS.Set", { key: key, value: value }, function (res, ec, em) {
    if (ec !== 0) print("KVS.Set error", key, ec, em);
    if (cb) cb();
  });
}

function kvsGet(key, cb) {
  Shelly.call("KVS.Get", { key: key }, function (res, ec, em) {
    if (ec !== 0) {
      cb(null);
      return;
    }
    cb(res && res.value !== undefined ? res.value : null);
  });
}

function saveState(cb) {
  // Plus Uni erlaubt max. 255 Zeichen pro KVS-Wert -> in mehrere Keys splitten.
  let s1 = JSON.stringify({
    i: round3(state.inTotal),
    o: round3(state.outTotal),
    t: round3(state.drinkTotal),
    li: round3(state.lastIn),
    lo: round3(state.lastOut),
  });
  let s2 = JSON.stringify({
    dk: state.dayKey,
    dis: round3(state.dayInStart),
    dos: round3(state.dayOutStart),
    wk: state.weekKey,
    wis: round3(state.weekInStart),
    wos: round3(state.weekOutStart),
    mk: state.monthKey,
    mis: round3(state.monthInStart),
    mos: round3(state.monthOutStart),
  });
  let s3 = JSON.stringify({
    yi: round3(state.yIn),
    yo: round3(state.yOut),
    yt: round3(state.yDrink),
    yk: state.yKey,
    lrd: state.lastReportDay,
    rfc: state.remoteFailCount,
    rof: state.remoteOffline ? 1 : 0,
  });
  let s4 = JSON.stringify({
    lwi: round3(state.lwIn),
    lwo: round3(state.lwOut),
    lwt: round3(state.lwDrink),
    lwk: state.lwKey,
    lmi: round3(state.lmIn),
    lmo: round3(state.lmOut),
    lmt: round3(state.lmDrink),
    lmk: state.lmKey,
  });

  let s5 = JSON.stringify(state.todayHourly);
  let s6 = JSON.stringify(state.yHourly);
  let s7 = JSON.stringify({
    e: round3(state.energyTotal),
    le: round3(state.lastEnergy),
    des: round3(state.dayEnergyStart),
    wes: round3(state.weekEnergyStart),
    mes: round3(state.monthEnergyStart),
    ye: round3(state.yEnergy),
    lwe: round3(state.lwEnergy),
    lme: round3(state.lmEnergy),
    pfc: state.plugFailCount,
    pof: state.plugOffline ? 1 : 0,
  });
  let s8 = JSON.stringify(state.todayEnergySlots);
  let s9 = JSON.stringify(state.yEnergySlots);

  kvsSet("osm.s1", s1, function () {
    kvsSet("osm.s2", s2, function () {
      kvsSet("osm.s3", s3, function () {
        kvsSet("osm.s4", s4, function () {
          kvsSet("osm.s5", s5, function () {
            kvsSet("osm.s6", s6, function () {
              kvsSet("osm.s7", s7, function () {
                kvsSet("osm.s8", s8, function () {
                  kvsSet("osm.s9", s9, cb);
                });
              });
            });
          });
        });
      });
    });
  });
}

function loadState(cb) {
  function parseJsonOrEmpty(val) {
    if (typeof val !== "string" || val === "") return {};
    try {
      return JSON.parse(val);
    } catch (e) {
      return {};
    }
  }

  kvsGet("osm.s1", function (v1) {
    kvsGet("osm.s2", function (v2) {
      kvsGet("osm.s3", function (v3) {
        kvsGet("osm.s4", function (v4) {
          kvsGet("osm.s5", function (v5) {
            kvsGet("osm.s6", function (v6) {
              kvsGet("osm.s7", function (v7) {
                kvsGet("osm.s8", function (v8) {
                  kvsGet("osm.s9", function (v9) {
                    let o1 = parseJsonOrEmpty(v1);
                    let o2 = parseJsonOrEmpty(v2);
                    let o3 = parseJsonOrEmpty(v3);
                    let o4 = parseJsonOrEmpty(v4);
                    let o7 = parseJsonOrEmpty(v7);

                    state.inTotal = o1.i || 0;
                    state.outTotal = o1.o || 0;
                    state.drinkTotal = o1.t || 0;
                    state.lastIn = o1.li || 0;
                    state.lastOut = o1.lo || 0;

                    state.dayKey = o2.dk || "";
                    state.dayInStart = o2.dis || 0;
                    state.dayOutStart = o2.dos || 0;
                    state.weekKey = o2.wk || "";
                    state.weekInStart = o2.wis || 0;
                    state.weekOutStart = o2.wos || 0;
                    state.monthKey = o2.mk || "";
                    state.monthInStart = o2.mis || 0;
                    state.monthOutStart = o2.mos || 0;

                    state.yIn = o3.yi || 0;
                    state.yOut = o3.yo || 0;
                    state.yDrink = o3.yt || 0;
                    state.yKey = o3.yk || "";
                    state.lastReportDay = o3.lrd || "";
                    state.remoteFailCount = o3.rfc || 0;
                    state.remoteOffline = (o3.rof || 0) === 1;

                    state.lwIn = o4.lwi || 0;
                    state.lwOut = o4.lwo || 0;
                    state.lwDrink = o4.lwt || 0;
                    state.lwKey = o4.lwk || "";
                    state.lmIn = o4.lmi || 0;
                    state.lmOut = o4.lmo || 0;
                    state.lmDrink = o4.lmt || 0;
                    state.lmKey = o4.lmk || "";

                    state.energyTotal = o7.e || 0;
                    state.lastEnergy = o7.le || 0;
                    state.dayEnergyStart = o7.des || 0;
                    state.weekEnergyStart = o7.wes || 0;
                    state.monthEnergyStart = o7.mes || 0;
                    state.yEnergy = o7.ye || 0;
                    state.lwEnergy = o7.lwe || 0;
                    state.lmEnergy = o7.lme || 0;
                    state.plugFailCount = o7.pfc || 0;
                    state.plugOffline = (o7.pof || 0) === 1;

                    let defWater = zero48Array();
                    let defEnergy = zero48Array();
                    try {
                      let a5 = JSON.parse(v5);
                      state.todayHourly = (a5 && a5.length === 48) ? a5 : zero48Array();
                    } catch (e) { state.todayHourly = defWater; }
                    try {
                      let a6 = JSON.parse(v6);
                      state.yHourly = (a6 && a6.length === 48) ? a6 : zero48Array();
                    } catch (e) { state.yHourly = zero48Array(); }
                    try {
                      let a8 = JSON.parse(v8);
                      state.todayEnergySlots = (a8 && a8.length === 48) ? a8 : defEnergy;
                    } catch (e) { state.todayEnergySlots = zero48Array(); }
                    try {
                      let a9 = JSON.parse(v9);
                      state.yEnergySlots = (a9 && a9.length === 48) ? a9 : zero48Array();
                    } catch (e) { state.yEnergySlots = zero48Array(); }

                    cb();
                  });
                });
              });
            });
          });
        });
      });
    });
  });
}

function fetchLocalIn(cb) {
  Shelly.call("Input.GetStatus", { id: CFG.inputId }, function (res, ec, em) {
    if (ec !== 0) {
      cb("local Input.GetStatus failed: " + em, 0);
      return;
    }
    cb(null, safeLitersFromStatus(res, "local"));
  });
}

function parseRemoteBody(result) {
  if (!result) return null;
  if (typeof result.body === "string" && result.body !== "") {
    try {
      return JSON.parse(result.body);
    } catch (e) {
      return null;
    }
  }
  if (result.body && typeof result.body === "object") return result.body;
  return null;
}

function fetchRemoteOut(cb) {
  Shelly.call(
    "HTTP.Request",
    {
      method: "GET",
      url: CFG.remoteAblaufStatusUrl,
      timeout: 10,
      ssl_ca: "*",
    },
    function (res, ec, em) {
      if (ec !== 0) {
        cb("remote HTTP failed: " + em, state.lastOut || 0);
        return;
      }
      let code = (res && res.code) || 0;
      if (code < 200 || code >= 300) {
        cb("remote HTTP status " + code, state.lastOut || 0);
        return;
      }
      let body = parseRemoteBody(res);
      if (!body) {
        cb("remote JSON parse failed", state.lastOut || 0);
        return;
      }
      cb(null, safeLitersFromStatus(body, "remote"));
    }
  );
}


function fetchRemotePlugEnergy(cb) {
  Shelly.call(
    "HTTP.Request",
    {
      method: "GET",
      url: CFG.remotePlugStatusUrl,
      timeout: 10,
      ssl_ca: "*",
    },
    function (res, ec, em) {
      if (ec !== 0) {
        cb("plug HTTP failed: " + em, state.lastEnergy || 0);
        return;
      }
      let code = (res && res.code) || 0;
      if (code < 200 || code >= 300) {
        cb("plug HTTP status " + code, state.lastEnergy || 0);
        return;
      }
      let body = parseRemoteBody(res);
      if (!body) {
        cb("plug JSON parse failed", state.lastEnergy || 0);
        return;
      }
      cb(null, safeEnergyKwhFromStatus(body, "plug"));
    }
  );
}

function sendWaReport(text, attempt) {
  Shelly.call(
    "HTTP.Request",
    {
      method: "POST",
      url: CFG.wahaUrl,
      timeout: 15,
      ssl_ca: "*",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Api-Key": CFG.wahaApiKey,
      },
      body: JSON.stringify({
        chatId: CFG.waChatId,
        text: text,
        session: CFG.waSession,
      }),
    },
    function (res, ec, em) {
      if (ec === 0 && res && res.code >= 200 && res.code < 300) {
        print("WAHA report sent.");
        return;
      }

      if (attempt < CFG.waRetries) {
        let waitMs = CFG.waRetryBaseSec * attempt * 1000;
        print("WAHA retry", attempt + 1, "in", waitMs, "ms");
        Timer.set(waitMs, false, function () {
          sendWaReport(text, attempt + 1);
        });
      } else {
        print("WAHA send failed:", ec, em, res ? res.code : "no-code");
      }
    }
  );
}

function markRemoteHealth(errOut) {
  if (errOut) {
    state.remoteFailCount = state.remoteFailCount + 1;
    if (state.remoteFailCount >= CFG.remoteOfflineFailThreshold) {
      state.remoteOffline = true;
    }
    return;
  }
  state.remoteFailCount = 0;
  state.remoteOffline = false;
}

function markPlugHealth(errPlug) {
  if (errPlug) {
    state.plugFailCount = state.plugFailCount + 1;
    if (state.plugFailCount >= CFG.remoteOfflineFailThreshold) {
      state.plugOffline = true;
    }
    return;
  }
  state.plugFailCount = 0;
  state.plugOffline = false;
}

function buildScheduledReport(now) {
  let dayEff = state.yIn > 0 ? (state.yDrink / state.yIn) * 100.0 : 0.0;
  let includeLastWeek = now.getDay() === 1 && !!state.lwKey; // Montag
  let includeLastMonth = now.getDate() === 1 && !!state.lmKey; // Monatserster
  let codeFence = "```";

  let txt =
    "💧 *Osmose Report*\n" +
    "🕒 Erstellt: " +
    dayKeyNow(now) +
    " " +
    todayHm(now) +
    "\n\n" +
    "📅 *Gestern* (" +
    state.yKey +
    ")\n" +
    codeFence +
    "\n" +
    tableRow("Zulauf", fmtL2(state.yIn)) +
    "\n" +
    tableRow("Abwasser", fmtL2(state.yOut)) +
    "\n" +
    tableRow("Produktwasser", fmtL2(state.yDrink)) +
    "\n" +
    tableRow("Ausbeute", fmtPct2(dayEff)) +
    "\n" +
    tableRow("Energie", fmtKwh2(state.yEnergy)) +
    "\n" +
    codeFence;

  if (includeLastWeek) {
    let weekEff = state.lwIn > 0 ? (state.lwDrink / state.lwIn) * 100.0 : 0.0;
    txt +=
      "\n\n" +
      "📆 *Letzte Woche* (" +
      state.lwKey +
      ")\n" +
      codeFence +
      "\n" +
      tableRow("Zulauf", fmtL2(state.lwIn)) +
      "\n" +
      tableRow("Abwasser", fmtL2(state.lwOut)) +
      "\n" +
      tableRow("Produktwasser", fmtL2(state.lwDrink)) +
      "\n" +
      tableRow("Ausbeute", fmtPct2(weekEff)) +
      "\n" +
      tableRow("Energie", fmtKwh2(state.lwEnergy)) +
      "\n" +
      codeFence;
  }

  if (includeLastMonth) {
    let monthEff = state.lmIn > 0 ? (state.lmDrink / state.lmIn) * 100.0 : 0.0;
    txt +=
      "\n\n" +
      "🗓️ *Letzter Monat* (" +
      state.lmKey +
      ")\n" +
      codeFence +
      "\n" +
      tableRow("Zulauf", fmtL2(state.lmIn)) +
      "\n" +
      tableRow("Abwasser", fmtL2(state.lmOut)) +
      "\n" +
      tableRow("Produktwasser", fmtL2(state.lmDrink)) +
      "\n" +
      tableRow("Ausbeute", fmtPct2(monthEff)) +
      "\n" +
      tableRow("Energie", fmtKwh2(state.lmEnergy)) +
      "\n" +
      codeFence;
  }

  if (state.remoteOffline) {
    txt +=
      "\n\n" +
      "⚠️ *Hinweis*\n" +
      "Ablauf-Shelly ist derzeit nicht erreichbar.\n" +
      "Der Ablaufwert wird temporaer mit dem letzten gueltigen Stand fortgeschrieben.";
  }
  if (state.plugOffline) {
    txt +=
      "\n\n" +
      "⚠️ *Hinweis*\n" +
      "Shelly Plug ist derzeit nicht erreichbar.\n" +
      "Der Energiewert wird temporaer mit dem letzten gueltigen Stand fortgeschrieben.";
  }

  return txt;
}

function buildTestReport(now) {
  let dayIn = state.inTotal - state.dayInStart;
  let dayOut = state.outTotal - state.dayOutStart;
  if (dayIn < 0) dayIn = 0;
  if (dayOut < 0) dayOut = 0;
  let dayDrink = clampDrink(dayIn, dayOut);
  let dayEff = dayIn > 0 ? (dayDrink / dayIn) * 100.0 : 0.0;
  let totalEff = state.inTotal > 0 ? (state.drinkTotal / state.inTotal) * 100.0 : 0.0;
  let dayEnergy = state.energyTotal - state.dayEnergyStart;
  if (dayEnergy < 0) dayEnergy = 0;
  let codeFence = "```";

  return (
    "🧪 *TEST Osmose Report*\n" +
    "🕒 Erstellt: " +
    dayKeyNow(now) +
    " " +
    todayHm(now) +
    "\n\n" +
    "📍 *Heute bisher*\n" +
    codeFence +
    "\n" +
    tableRow("Zulauf", fmtL2(dayIn)) +
    "\n" +
    tableRow("Abwasser", fmtL2(dayOut)) +
    "\n" +
    tableRow("Produktwasser", fmtL2(dayDrink)) +
    "\n" +
    tableRow("Ausbeute", fmtPct2(dayEff)) +
    "\n" +
    tableRow("Energie", fmtKwh2(dayEnergy)) +
    "\n" +
    codeFence +
    "\n\n" +
    "🏁 *Gesamt seit Start*\n" +
    codeFence +
    "\n" +
    tableRow("Zulauf", fmtL2(state.inTotal)) +
    "\n" +
    tableRow("Abwasser", fmtL2(state.outTotal)) +
    "\n" +
    tableRow("Produktwasser", fmtL2(state.drinkTotal)) +
    "\n" +
    tableRow("Ausbeute", fmtPct2(totalEff)) +
    "\n" +
    tableRow("Energie", fmtKwh2(state.energyTotal)) +
    "\n" +
    codeFence +
    (state.remoteOffline
      ? "\n\n⚠️ *Hinweis*\nAblauf-Shelly ist derzeit nicht erreichbar."
      : "") +
    (state.plugOffline
      ? "\n\n⚠️ *Hinweis*\nShelly Plug ist derzeit nicht erreichbar."
      : "")
  );
}

function processPeriods(now) {
  let dKey = dayKeyNow(now);
  let wKey = weekKeyNow(now);
  let mKey = monthKeyNow(now);

  if (!state.initialized) {
    state.dayKey = dKey;
    state.dayInStart = state.inTotal;
    state.dayOutStart = state.outTotal;
    state.dayEnergyStart = state.energyTotal;
    state.weekKey = wKey;
    state.weekInStart = state.inTotal;
    state.weekOutStart = state.outTotal;
    state.weekEnergyStart = state.energyTotal;
    state.monthKey = mKey;
    state.monthInStart = state.inTotal;
    state.monthOutStart = state.outTotal;
    state.monthEnergyStart = state.energyTotal;
    state.lastIn = state.inTotal;
    state.lastOut = state.outTotal;
    state.lastEnergy = state.energyTotal;
    state.initialized = true;
    return;
  }

  // Tageswechsel: Vortag abschliessen mit den letzten bekannten Totals.
  if (state.dayKey !== dKey) {
    state.yIn = state.lastIn - state.dayInStart;
    state.yOut = state.lastOut - state.dayOutStart;
    state.yEnergy = state.lastEnergy - state.dayEnergyStart;
    if (state.yIn < 0) state.yIn = 0;
    if (state.yOut < 0) state.yOut = 0;
    if (state.yEnergy < 0) state.yEnergy = 0;
    state.yDrink = clampDrink(state.yIn, state.yOut);
    state.yKey = state.dayKey;

    // 30-Min-Slots des Vortags sichern, heute-Array zuruecksetzen
    state.yHourly = state.todayHourly;
    state.todayHourly = zero48Array();
    state.yEnergySlots = state.todayEnergySlots;
    state.todayEnergySlots = zero48Array();

    state.dayKey = dKey;
    state.dayInStart = state.inTotal;
    state.dayOutStart = state.outTotal;
    state.dayEnergyStart = state.energyTotal;
  }

  if (state.weekKey !== wKey) {
    let prevWeekIn = state.lastIn - state.weekInStart;
    let prevWeekOut = state.lastOut - state.weekOutStart;
    let prevWeekEnergy = state.lastEnergy - state.weekEnergyStart;
    if (prevWeekIn < 0) prevWeekIn = 0;
    if (prevWeekOut < 0) prevWeekOut = 0;
    if (prevWeekEnergy < 0) prevWeekEnergy = 0;
    state.lwIn = prevWeekIn;
    state.lwOut = prevWeekOut;
    state.lwDrink = clampDrink(prevWeekIn, prevWeekOut);
    state.lwEnergy = prevWeekEnergy;
    state.lwKey = state.weekKey;

    state.weekKey = wKey;
    state.weekInStart = state.inTotal;
    state.weekOutStart = state.outTotal;
    state.weekEnergyStart = state.energyTotal;
  }

  if (state.monthKey !== mKey) {
    let prevMonthIn = state.lastIn - state.monthInStart;
    let prevMonthOut = state.lastOut - state.monthOutStart;
    let prevMonthEnergy = state.lastEnergy - state.monthEnergyStart;
    if (prevMonthIn < 0) prevMonthIn = 0;
    if (prevMonthOut < 0) prevMonthOut = 0;
    if (prevMonthEnergy < 0) prevMonthEnergy = 0;
    state.lmIn = prevMonthIn;
    state.lmOut = prevMonthOut;
    state.lmDrink = clampDrink(prevMonthIn, prevMonthOut);
    state.lmEnergy = prevMonthEnergy;
    state.lmKey = state.monthKey;

    state.monthKey = mKey;
    state.monthInStart = state.inTotal;
    state.monthOutStart = state.outTotal;
    state.monthEnergyStart = state.energyTotal;
  }
}

// URL-Kodierung fuer Chart-Config (mJS hat kein encodeURIComponent)
function urlEncodeChart(s) {
  let out = "";
  let i = 0;
  while (i < s.length) {
    let c = s[i];
    if (c === "\"") out += "%22";
    else if (c === " ") out += "%20";
    else if (c === "&") out += "%26";
    else if (c === "=") out += "%3D";
    else if (c === "%") out += "%25";
    else if (c === "#") out += "%23";
    else if (c === "+") out += "%2B";
    else out += c;
    i++;
  }
  return out;
}

// Baut quickchart.io/chart URL (offizieller Endpoint) fuer 30-Min-Verlauf.
// yHourly: Array[48] in 1/10 Liter, Slot 0 = 00:00-00:30.
function buildSparkUrl(yHourly, yEnergySlots, dayLabel) {
  let waterArr = [];
  let energyArr = [];
  let i = 0;
  while (i < 48) {
    waterArr.push(Math.round(yHourly[i]) / 10);
    energyArr.push(Math.round(yEnergySlots[i]) / 100);
    i++;
  }
  // X-Achse: Uhrzeiten 00:00, 00:30, 01:00, ... 23:30 (Slot j = 2*h + m/30)
  let labels = [];
  let j = 0;
  while (j < 48) {
    let h = Math.floor(j / 2);
    let m = (j % 2) * 30;
    labels.push(z(h) + ":" + z(m));
    j++;
  }
  let cfg = {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        { label: "Produktwasser L", yAxisID: "yL", data: waterArr, backgroundColor: "rgba(25,118,210,0.60)" },
        { type: "line", label: "Energie kWh", yAxisID: "yE", data: energyArr, fill: false, pointRadius: 0, borderWidth: 2, borderColor: "rgba(245,124,0,1)", backgroundColor: "rgba(245,124,0,1)" }
      ],
    },
    options: {
      title: { display: true, text: "Produktwasser + Energie " + dayLabel },
      scales: { yAxes: [
        { id: "yL", position: "left", ticks: { beginAtZero: true } },
        { id: "yE", position: "right", ticks: { beginAtZero: true }, gridLines: { drawOnChartArea: false } }
      ] },
    },
  };
  let json = JSON.stringify(cfg);
  return "https://quickchart.io/chart?w=640&h=320&bkg=white&c=" + urlEncodeChart(json);
}

function sendWaChart(chartUrl, caption, attempt) {
  // WAHA /api/sendImage mit externem Bild-URL (WAHA holt das Bild von quickchart.io)
  let imgEndpoint = CFG.wahaUrl.replace("sendText", "sendImage");
  Shelly.call(
    "HTTP.Request",
    {
      method: "POST",
      url: imgEndpoint,
      timeout: 20,
      ssl_ca: "*",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Api-Key": CFG.wahaApiKey,
      },
      body: JSON.stringify({
        chatId: CFG.waChatId,
        session: CFG.waSession,
        caption: caption,
        file: {
          url: chartUrl,
          filename: "produktwasser.png",
          mimetype: "image/png",
        },
      }),
    },
    function (res, ec, em) {
      if (ec === 0 && res && res.code >= 200 && res.code < 300) {
        print("WAHA chart sent.");
        return;
      }
      if (attempt < CFG.waRetries) {
        let waitMs = CFG.waRetryBaseSec * attempt * 1000;
        print("WAHA chart retry", attempt + 1, "in", waitMs, "ms");
        Timer.set(waitMs, false, function () {
          sendWaChart(chartUrl, caption, attempt + 1);
        });
      } else {
        print("WAHA chart failed:", ec, em, res ? res.code : "no-code");
      }
    }
  );
}

function maybeSendDaily(now) {
  let dKey = dayKeyNow(now);
  if (now.getHours() !== CFG.dailySendHour) return;
  if (state.lastReportDay === dKey) return; // heute schon gesendet
  if (!state.yKey) return; // noch kein Vortag vorhanden

  // Zuerst Diagramm senden, dann 3 Sekunden spaeter den Textbericht
  let chartUrl = buildSparkUrl(state.yHourly, state.yEnergySlots, state.yKey);
  sendWaChart(chartUrl, "📊 Produktwasser + Energie " + state.yKey, 1);

  let text = buildScheduledReport(now);
  Timer.set(3000, false, function () {
    sendWaReport(text, 1);
  });

  state.lastReportDay = dKey;
}

function doTick(doneCb) {
  if (busy) return;
  busy = true;

  fetchLocalIn(function (errIn, inL) {
    if (errIn) {
      print(errIn);
      busy = false;
      return;
    }

    fetchRemoteOut(function (errOut, outL) {
      if (errOut) print(errOut);
      markRemoteHealth(errOut);

      fetchRemotePlugEnergy(function (errPlug, energyKwh) {
        if (errPlug) print(errPlug);
        markPlugHealth(errPlug);

        state.inTotal = round3(inL);
        state.outTotal = round3(outL);
        state.drinkTotal = round3(clampDrink(state.inTotal, state.outTotal));
        state.energyTotal = round3(energyKwh);

        let now = new Date();
        processPeriods(now);

        // 30-Min-Delta Produktwasser/Energie akkumulieren (nach Initialisierung und Tag-Rollover)
        if (state.initialized) {
          let prevProd = clampDrink(state.lastIn, state.lastOut);
          let deltaWater = state.drinkTotal - prevProd;
          let deltaEnergy = state.energyTotal - state.lastEnergy;
          let slot = now.getHours() * 2 + (now.getMinutes() >= 30 ? 1 : 0);
          if (deltaWater > 0) {
            state.todayHourly[slot] = state.todayHourly[slot] + Math.round(deltaWater * 10);
          }
          if (deltaEnergy > 0) {
            state.todayEnergySlots[slot] = state.todayEnergySlots[slot] + Math.round(deltaEnergy * 100);
          }
        }

        maybeSendDaily(now);

        state.lastIn = state.inTotal;
        state.lastOut = state.outTotal;
        state.lastEnergy = state.energyTotal;

        saveState(function () {
          print(
            "in=" +
              state.inTotal +
              "L out=" +
              state.outTotal +
              "L drink=" +
              state.drinkTotal +
              "L energy=" +
              state.energyTotal +
              "kWh y=" +
              state.yDrink +
              "L yE=" +
              state.yEnergy +
              "kWh remoteOffline=" +
              (state.remoteOffline ? "yes" : "no") +
              " plugOffline=" +
              (state.plugOffline ? "yes" : "no")
          );
          busy = false;
          if (doneCb) doneCb();
        });
      });
    });
  });
}

function validateConfig() {
  if (CFG.wahaApiKey === "CHANGE_ME") {
    print("WARN: Bitte CFG.wahaApiKey setzen.");
  }
  if (!CFG.remotePlugStatusUrl) {
    print("WARN: Bitte CFG.remotePlugStatusUrl setzen.");
  }
}

function start() {
  validateConfig();
  loadState(function () {
    // Sofort einmal rechnen (Initialisierung und initiale Werte)
    doTick(function () {
      if (CFG.sendTestOnStart) {
        let now = new Date();
        let testText = buildTestReport(now);
        sendWaReport(testText, 1);
        print("Test report triggered on start.");
      }
      if (CFG.sendDailyReportTestOnStart) {
        let now = new Date();
        let chartData = state.yKey ? state.yHourly : state.todayHourly;
        let energyChartData = state.yKey ? state.yEnergySlots : state.todayEnergySlots;
        let chartLabel = state.yKey ? state.yKey : dayKeyNow(now) + " (Test)";
        let chartUrl = buildSparkUrl(chartData, energyChartData, chartLabel);
        sendWaChart(chartUrl, "📊 Produktwasser + Energie " + chartLabel + " (Test)", 1);
        let reportText = state.yKey ? buildScheduledReport(now) : buildTestReport(now);
        Timer.set(3000, false, function () {
          sendWaReport(reportText, 1);
          print("Daily report test (Chart + Text) sent.");
        });
      }
    });

    // Timer auf naechste :00 oder :30 Marke ausrichten, dann alle 30 Min
    let n = new Date();
    let minRemainder = n.getMinutes() % 30;
    let secInSlot = minRemainder * 60 + n.getSeconds();
    let msToNext = (1800 - secInSlot) * 1000 - n.getMilliseconds();
    print("Master script started. Naechster Tick in " + Math.round(msToNext / 1000) + "s.");
    Timer.set(msToNext, false, function () {
      doTick(null);
      Timer.set(CFG.tickSeconds * 1000, true, doTick);
    });
  });
}

start();

