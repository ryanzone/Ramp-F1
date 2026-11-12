// Run with: node --test src/replayModel.test.js
import test from "node:test";
import assert from "node:assert/strict";
import {
  applyEvents, emptyStore, fromSnapshot, standings, sectorBoard, currentStint, raceStatus,
  lapRows, stintRows, pitRows, formatClock, parseClock, formatDelta, teamColor, compoundInfo,
} from "./replayModel.js";

const drivers = [
  { driver_number: 1, code: "NOR", name: "Lando NORRIS", team: "McLaren" },
  { driver_number: 3, code: "VER", name: "Max VERSTAPPEN", team: "Red Bull Racing" },
];
const byNumber = Object.fromEntries(drivers.map((d) => [d.driver_number, d]));
const lap = (n, lapNo, dur, s = [30, 30, 30], extra = {}) => ({
  t: `2026-01-01T10:0${lapNo}:00+00:00`, kind: "lap_complete", driver_number: n, lap_number: lapNo,
  data: { lap_duration: dur, sector_1: s[0], sector_2: s[1], sector_3: s[2], st_speed: 300, is_valid: true, ...extra },
});

test("applyEvents never mutates the previous store", () => {
  const a = emptyStore();
  const b = applyEvents(a, [lap(1, 1, 90)]);
  assert.equal(a.lapCount, 0);
  assert.deepEqual(a.lapsByDriver, {});
  assert.equal(b.lapCount, 1);
  const c = applyEvents(b, [lap(1, 2, 91)]);
  assert.equal(b.lapsByDriver[1].length, 1);
  assert.equal(c.lapsByDriver[1].length, 2);
});

test("an empty batch returns the same store (no re-render)", () => {
  const a = fromSnapshot([lap(1, 1, 90)]);
  assert.equal(applyEvents(a, []), a);
});

test("snapshot then incremental events equals folding everything at once", () => {
  const events = [lap(1, 1, 90), lap(3, 1, 91), lap(1, 2, 89)];
  const incremental = applyEvents(fromSnapshot(events.slice(0, 2)), events.slice(2));
  assert.deepEqual(incremental, fromSnapshot(events));
});

test("standings are ordered by position with gaps and tyres", () => {
  const events = [
    { t: "2026-01-01T10:00:01+00:00", kind: "position", driver_number: 3, data: { position: 1 } },
    { t: "2026-01-01T10:00:01+00:00", kind: "position", driver_number: 1, data: { position: 2 } },
    { t: "2026-01-01T10:00:02+00:00", kind: "interval", driver_number: 1, data: { gap_to_leader: 2.47, interval_ahead: 2.47 } },
    { t: "2026-01-01T10:00:03+00:00", kind: "position", driver_number: 1, data: { position: 1 } },
    { t: "2026-01-01T10:00:03+00:00", kind: "position", driver_number: 3, data: { position: 2 } },
    { t: "2026-01-01T10:00:00+00:00", kind: "stint", driver_number: 1, lap_number: 1,
      data: { stint_number: 1, compound: "MEDIUM", start_lap: 1, starting_tyre_age: 0, phase: "start", end_lap: null } },
    lap(1, 1, 90), lap(1, 2, 89),
  ];
  const rows = standings(fromSnapshot(events), drivers);
  assert.deepEqual(rows.map((r) => r.code), ["NOR", "VER"]);
  assert.equal(rows[0].stint.compound, "MEDIUM");
  assert.equal(rows[0].stint.tyre_age, 2);
  assert.equal(rows[0].gap, 2.47);
  assert.equal(rows[0].lastLap, 89);
});

test("an older position sample never overwrites a newer one", () => {
  const s = applyEvents(emptyStore(), [
    { t: "2026-01-01T10:00:05+00:00", kind: "position", driver_number: 1, data: { position: 3 } },
    { t: "2026-01-01T10:00:01+00:00", kind: "position", driver_number: 1, data: { position: 9 } },
  ]);
  assert.equal(s.positions[1].position, 3);
});

test("sector board compares with the driver's own earlier best", () => {
  const s = fromSnapshot([lap(1, 1, 90, [30, 30, 30]), lap(1, 2, 89, [29.5, 30.2, 29.3])]);
  const b = sectorBoard(s, 1);
  assert.equal(b.lap, 2);
  assert.ok(Math.abs(b.s1.delta + 0.5) < 1e-9);
  assert.ok(Math.abs(b.s2.delta - 0.2) < 1e-9);
  assert.ok(Math.abs(b.lapDelta + 1) < 1e-9);
  assert.equal(sectorBoard(emptyStore(), 1), null);
});

test("ended stints are reported finished and running stints are clipped to the last lap", () => {
  const start = (n, c, startLap) => ({ t: "2026-01-01T10:00:00+00:00", kind: "stint", driver_number: 1, lap_number: startLap,
    data: { stint_number: n, compound: c, start_lap: startLap, starting_tyre_age: 0, phase: "start", end_lap: null } });
  const end = { t: "2026-01-01T10:09:00+00:00", kind: "stint", driver_number: 1, lap_number: 3,
    data: { stint_number: 1, compound: "SOFT", start_lap: 1, starting_tyre_age: 0, phase: "end", end_lap: 3 } };
  const s = fromSnapshot([start(1, "SOFT", 1), lap(1, 1, 90), lap(1, 2, 90), lap(1, 3, 90), end, start(2, "HARD", 4), lap(1, 4, 90), lap(1, 5, 90)]);
  const rows = stintRows(s, byNumber);
  assert.deepEqual(rows.map((r) => [r.stint_number, r.start_lap, r.end_lap, r.running]), [[1, 1, 3, false], [2, 4, 5, true]]);
  assert.equal(currentStint(s, 1).compound, "HARD");
  assert.equal(currentStint(s, 1).tyre_age, 2);
});

test("race status follows the latest track message", () => {
  const rc = (message, flag = null) => ({ t: "2026-01-01T10:00:00+00:00", kind: "race_control", driver_number: null, lap_number: 1, data: { message, flag, category: "Flag" } });
  assert.equal(raceStatus(emptyStore()).label, "Awaiting start");
  assert.equal(raceStatus(fromSnapshot([rc("GREEN LIGHT - PIT EXIT OPEN", "GREEN")])).label, "Green flag");
  assert.equal(raceStatus(fromSnapshot([rc("GREEN LIGHT", "GREEN"), rc("VSC DEPLOYED")])).label, "Virtual safety car");
  assert.equal(raceStatus(fromSnapshot([rc("SAFETY CAR DEPLOYED"), rc("CLEAR", "CLEAR")])).label, "Green flag");
  assert.equal(raceStatus(fromSnapshot([rc("RED FLAG", "RED")])).tone, "bad");
});

test("adapters give the existing panels their row shapes", () => {
  const s = fromSnapshot([lap(1, 1, 90), { t: "2026-01-01T10:00:00+00:00", kind: "pit_stop", driver_number: 3, lap_number: 2,
    data: { stop_number: 1, entered_at: "2026-01-01T10:00:00+00:00", lane_duration: 22, stop_duration: 2.4 } }]);
  assert.deepEqual(lapRows(s, byNumber), [{ driver_code: "NOR", lap_number: 1, lap_time_seconds: 90, is_valid: true }]);
  assert.equal(pitRows(s, byNumber)[0].driver_code, "VER");
  assert.equal(pitRows(s, byNumber)[0].stop_duration_seconds, 2.4);
});

test("time helpers", () => {
  assert.equal(formatClock(3725), "1:02:05");
  assert.equal(formatClock(-4), "0:00:00");
  assert.equal(parseClock("1:02:05"), 3725);
  assert.equal(parseClock("12:30"), 750);
  assert.equal(parseClock("90"), 90);
  assert.equal(parseClock("a:b"), null);
  assert.equal(parseClock("1:2:3:4"), null);
  assert.equal(formatDelta(-0.124), "−0.124");
  assert.equal(formatDelta(0.052), "+0.052");
  assert.equal(formatDelta(null), "—");
});

test("colours: known teams, stable fallbacks, compounds", () => {
  assert.equal(teamColor("Ferrari"), "#e80020");
  assert.equal(teamColor("Unknown Team"), teamColor("Unknown Team"));
  assert.equal(compoundInfo("hard").letter, "H");
  assert.equal(compoundInfo(null).letter, "?");
});
