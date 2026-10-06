import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { familyState, Family, Guardian, surnameOf } from "../src/screens/famiglie/model";
import { QrSvg } from "../src/screens/famiglie/Qr";
import { hubsFor, sectionsFor } from "../src/app/Shell";

const g = (status: Guardian["status"]): Guardian => ({ id: "g", legacy: false, family: "f", name: "Maria Bianchi", email: "m@x.it", phone: "", relationship: "PARENT", permissions: null, status, invitation: null, account: null, students: [], links: [], version: 1 });
const fam = (guardians: Guardian[], kids = 1): Family => ({ id: "f", reference: "Famiglia Bianchi", contact_name: "", contact_email: "", contact_phone: "", students: [], version: 1, guardians,
  children: Array.from({ length: kids }, (_, i) => ({ id: "c" + i, family: "f", display_name: "Luca", level: "", active: true, has_account: false, birth_date: null, version: 1 })) });

test("lo stato della famiglia mostra la cosa più urgente", () => {
  assert.deepEqual(familyState(fam([])), ["Manca un genitore", "red"]);
  assert.deepEqual(familyState(fam([g("ACTIVE"), g("TO_VERIFY")])), ["Da verificare", "amber"]);
  assert.deepEqual(familyState(fam([g("EXPIRED")])), ["Invito scaduto", "red"]);
  assert.deepEqual(familyState(fam([g("INVITED")])), ["Invito inviato", "blue"]);
  assert.deepEqual(familyState(fam([g("ACTIVE")], 0)), ["Nessun figlio", "amber"]);
  assert.deepEqual(familyState(fam([g("ACTIVE"), g("INVITED")])), ["Tutto attivo", "green"]);
});

test("il nome della famiglia si propone dal cognome del genitore", () => {
  assert.equal(surnameOf("Maria  De Luca"), "Luca");
  assert.equal(surnameOf("Maria"), "");
});

test("il QR code è un SVG con moduli scuri", () => {
  const html = renderToStaticMarkup(<QrSvg text="https://centro.example/invito#token=abc" />);
  assert.match(html, /^<svg[^>]+role="img"/);
  assert.match(html, /<path d="M\d/);
});

test("per il centro i figli stanno in Famiglie: niente sezione Studenti", () => {
  const keys = sectionsFor(true, ["CENTER"]).map((s) => s.key);
  assert.ok(keys.includes("anagrafica") && !keys.includes("studenti"));
  const persone = hubsFor(true, ["CENTER"]).find((h) => h.key === "persone")!;
  assert.deepEqual(persone.sections.map((s) => s.key), ["anagrafica", "tutor", "impegni"]);
  assert.ok(sectionsFor(false, ["GUARDIAN"]).some((s) => s.key === "studenti"));
});
