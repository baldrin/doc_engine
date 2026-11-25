"""Sample material: fictional documents and sample flows, so the engine can be shown
without any real document. Two flows read one long document; two read several short ones. Everything here is invented. Every page says so in its footer.

Pages are rendered as scanned-looking bilevel images (about 20 KB each), as in the POC, where
Sonnet 5.5 was confirmed to read them.
"""
from __future__ import annotations

import io
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import Section
from .db import Db, Jsonb
from .documents import store_document

W, H = 850, 1100
FOOTER = "Synthetic document generated for software testing. All names, dates and values are invented."


def _font(size: int) -> Any:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_page(rng: random.Random, file_name: str, page_no: int, blocks: list[tuple]) -> Image.Image:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    margin = 68
    body, head, small = _font(17), _font(22), _font(13)
    d.text((margin, 30), f"[{file_name} page {page_no}]", fill=0, font=_font(15))
    y = 78
    max_w = W - 2 * margin

    def para(text: str, font: Any, gap: int = 25) -> None:
        nonlocal y
        line: list[str] = []
        for w in text.split():
            if d.textlength(" ".join(line + [w]), font=font) > max_w and line:
                d.text((margin, y), " ".join(line), fill=15, font=font)
                y += gap
                line = [w]
            else:
                line.append(w)
        if line:
            d.text((margin, y), " ".join(line), fill=15, font=font)
            y += gap

    for b in blocks:
        if y > H - 120:
            break
        kind = b[0]
        if kind == "h":
            y += 6
            d.text((margin, y), b[1], fill=0, font=head)
            y += 34
            d.line((margin, y - 4, W - margin, y - 4), fill=0, width=2)
            y += 6
        elif kind == "p":
            para(b[1], body)
            y += 10
        elif kind == "kv":
            for k, v in b[1]:
                d.text((margin, y), f"{k}:", fill=0, font=body)
                d.text((margin + 190, y), str(v), fill=15, font=body)
                y += 25
            y += 10
        elif kind == "table":
            header, rows = b[1], b[2]
            xs = [margin + int(max_w * f) for f in b[3]]
            for x, h in zip(xs, header):
                d.text((x, y), h, fill=0, font=body)
            y += 26
            d.line((margin, y - 3, W - margin, y - 3), fill=0, width=2)
            for r in rows:
                if y > H - 120:
                    break
                for x, c in zip(xs, r):
                    d.text((x, y + 3), str(c), fill=15, font=body)
                y += 27
            y += 12
    d.text((margin, H - 56), FOOTER, fill=40, font=small)
    img = img.rotate(rng.uniform(-0.9, 0.9), resample=Image.BILINEAR, fillcolor=255)
    d = ImageDraw.Draw(img)
    for _ in range(rng.randint(120, 380)):
        x, yy = rng.randrange(W), rng.randrange(H)
        r = rng.randint(1, 2)
        d.rectangle((x, yy, x + r, yy + r), fill=rng.randint(0, 110))
    img = img.filter(ImageFilter.GaussianBlur(0.45))
    t = rng.randint(145, 168)
    return img.point(lambda v, t=t: 255 if v > t else 0).convert("1")


def to_pdf(images: list[Image.Image]) -> bytes:
    buf = io.BytesIO()
    images[0].save(buf, "PDF", save_all=True, append_images=images[1:], resolution=96.0)
    return buf.getvalue()


# ---------------------------------------------------------------- fictional patient record

PATIENT = "Avery T. Samplewood"
CLINIC = "Northfield Example Clinic"
CLINICIANS = ["Dr. M. Placeholder", "Dr. R. Testwell", "Dr. L. Mockford", "NP J. Fixture"]
PROBLEMS = ["type 2 diabetes", "hypertension", "chronic lower back pain", "seasonal asthma", "iron deficiency anemia",
            "hyperlipidemia"]
MEDS = [("Metformin", "500 mg", "twice daily"), ("Lisinopril", "10 mg", "once daily"),
        ("Atorvastatin", "20 mg", "at bedtime"), ("Albuterol inhaler", "90 mcg", "as needed"),
        ("Ferrous sulfate", "325 mg", "once daily"), ("Ibuprofen", "400 mg", "as needed with food")]
LABS = [("Hemoglobin", "g/dL", 12.0, 16.0), ("Hemoglobin A1c", "%", 4.0, 5.6), ("Glucose, fasting", "mg/dL", 70, 99),
        ("Creatinine", "mg/dL", 0.6, 1.2), ("Sodium", "mmol/L", 135, 145), ("Potassium", "mmol/L", 3.5, 5.1),
        ("LDL cholesterol", "mg/dL", 0, 100), ("Ferritin", "ng/mL", 30, 300), ("TSH", "mIU/L", 0.4, 4.0),
        ("ALT", "U/L", 7, 56)]


def _date(rng: random.Random, i: int, n: int) -> str:
    month = 1 + (i * 23 // max(1, n)) % 12
    year = 2023 + (i * 23 // max(1, n)) // 12
    return f"{year}-{month:02d}-{rng.randint(1, 28):02d}"


def patient_page(rng: random.Random, i: int, n: int) -> list[tuple]:
    date = _date(rng, i, n)
    who = rng.choice(CLINICIANS)
    head = [("kv", [("Patient", PATIENT), ("Record number", "EX-0042-TEST"), ("Date", date), ("Clinician", who)])]
    roll = rng.random()
    if i == 0:
        return [("h", f"{CLINIC}: Patient Record"), *head,
                ("p", "This record collects visit notes, laboratory reports, imaging reports, medication lists and "
                      "letters for one fictional patient over about two years. It exists only to test document software."),
                ("p", f"Active problems on file: {', '.join(PROBLEMS)}.")]
    if roll < 0.09:
        rows = []
        for name, unit, lo, hi in rng.sample(LABS, rng.randint(5, 8)):
            span = hi - lo
            v = rng.uniform(lo - 0.25 * span, hi + 0.35 * span)
            flag = "H" if v > hi else "L" if v < lo else ""
            fmt = f"{v:.1f}" if hi < 30 else f"{v:.0f}"
            rows.append((name, fmt, unit, f"{lo}-{hi}", flag))
        return [("h", "Laboratory Report"), *head,
                ("kv", [("Specimen", "Venous blood"), ("Collected", date + " 08:10"), ("Status", "Final")]),
                ("table", ("Test", "Result", "Unit", "Reference", "Flag"), rows, (0, 0.38, 0.52, 0.68, 0.9)),
                ("p", "Results outside the reference range are flagged H (high) or L (low). "
                      "Interpret together with the clinical picture.")]
    if roll < 0.17:
        rows = [(m, dose, freq) for m, dose, freq in rng.sample(MEDS, rng.randint(3, 6))]
        return [("h", "Medication List"), *head,
                ("table", ("Medication", "Dose", "Frequency"), rows, (0, 0.45, 0.65)),
                ("p", rng.choice(["No changes were made at this review.",
                                  "Metformin was increased after the last A1c result.",
                                  "Ibuprofen is to be limited because of the kidney function trend.",
                                  "The patient reports taking all medication as prescribed."]))]
    if roll < 0.24:
        area = rng.choice(["lumbar spine", "chest", "left knee", "abdomen"])
        return [("h", f"Imaging Report: {area.title()}"), *head,
                ("kv", [("Study", rng.choice(["X-ray, two views", "Ultrasound", "MRI without contrast"])),
                        ("Indication", rng.choice(["persistent pain", "follow up", "shortness of breath"]))]),
                ("p", "Findings: " + rng.choice([
                    "Mild degenerative change at L4 to L5 with preserved disc height. No fracture.",
                    "Lungs are clear. Heart size is normal. No effusion.",
                    "Small joint effusion. No acute bony abnormality.",
                    "Liver and gallbladder appear normal. No free fluid."])),
                ("p", "Impression: " + rng.choice(["No acute abnormality.", "Mild chronic change, stable since the prior study.",
                                                   "Findings consistent with the clinical history."]))]
    if roll < 0.30:
        return [("h", "Referral Letter"), *head,
                ("p", f"Dear colleague, I am referring {PATIENT} for assessment of {rng.choice(PROBLEMS)}. "
                      "Symptoms have continued despite first line treatment over the past three months."),
                ("p", "Relevant history, current medication and recent results are enclosed. "
                      "Please advise on further management and whether follow up with you is needed."),
                ("p", f"Yours sincerely, {who}, {CLINIC}.")]
    if roll < 0.35:
        return [("h", "Discharge Summary"), *head,
                ("kv", [("Admitted", date), ("Length of stay", f"{rng.randint(1, 4)} days"),
                        ("Reason", rng.choice(["asthma flare", "dehydration", "observation after a fall"]))]),
                ("p", "Course: the patient improved with standard treatment and was stable on the day of discharge. "
                      "No complications were recorded."),
                ("p", "Plan: continue usual medication, see the primary clinician within two weeks, "
                      "return sooner if symptoms worsen.")]
    prob = rng.choice(PROBLEMS)
    bp = f"{rng.randint(112, 152)}/{rng.randint(68, 96)}"
    return [("h", "Progress Note"), *head,
            ("p", f"Subjective: seen for {prob}. " + rng.choice([
                "Reports feeling generally well with no new complaints.",
                "Describes more fatigue over the last month and poorer sleep.",
                "Pain is worse after long periods of sitting and eases with walking.",
                "Home readings have been higher than at the last visit."])),
            ("p", f"Objective: blood pressure {bp} mmHg, pulse {rng.randint(58, 96)}, weight {rng.randint(68, 94)} kg. "
                  + rng.choice(["Examination is unremarkable.", "Mild tenderness over the lower back.",
                                "Chest is clear on auscultation.", "No ankle swelling."])),
            ("p", "Assessment: " + rng.choice([f"{prob}, stable.", f"{prob}, not at target.",
                                               f"{prob}, improving on current treatment."])),
            ("p", "Plan: " + rng.choice(["Continue current treatment and review in three months.",
                                         "Repeat blood tests before the next visit.",
                                         "Increase the dose and recheck in six weeks.",
                                         "Refer for physiotherapy and review after the course."]))]


# ---------------------------------------------------------------- fictional contract file

VENDOR, CLIENT = "Harborline Example Services Ltd", "Meridian Sample Cooperative"
CLAUSES = [
    ("Scope of Services", "The vendor will provide facilities maintenance at the sites listed in Schedule A, "
                          "including scheduled inspections, reactive repairs and a staffed help desk during business hours."),
    ("Term and Renewal", "The agreement runs for thirty six months from the effective date and renews for successive "
                         "twelve month periods unless either party gives ninety days written notice."),
    ("Fees and Payment", "The client will pay the monthly fee in Schedule B within thirty days of a correct invoice. "
                         "Late amounts carry interest at one percent per month."),
    ("Service Levels", "Urgent faults are attended within four hours and standard faults within two business days. "
                       "Missed service levels earn a credit of five percent of the monthly fee per event."),
    ("Liability", "Each party's total liability in a contract year is limited to the fees paid in that year, "
                  "except for death, personal injury or fraud."),
    ("Termination", "Either party may terminate for material breach that is not remedied within thirty days of notice. "
                    "The client may terminate for convenience on one hundred and eighty days notice."),
    ("Confidentiality", "Each party will keep the other's confidential information secret for five years "
                        "after the agreement ends and use it only to perform the agreement."),
    ("Insurance", "The vendor will hold public liability cover of at least five million per claim and provide "
                  "certificates on request."),
]
ITEMS = ["Scheduled inspection", "Reactive repair, electrical", "Reactive repair, plumbing", "Help desk service",
         "Filter replacement", "Emergency call out", "Fire system test", "Lift maintenance"]


def contract_page(rng: random.Random, i: int, n: int) -> list[tuple]:
    date = _date(rng, i, n)
    if i == 0:
        return [("h", "Master Services Agreement"),
                ("kv", [("Vendor", VENDOR), ("Client", CLIENT), ("Effective date", "2023-02-01"), ("Reference", "MSA-TEST-0117")]),
                ("p", "This file holds the agreement, its amendments, schedules, invoices and letters between two "
                      "fictional organisations. It exists only to test document software.")]
    roll = rng.random()
    if roll < 0.14:
        rows, total = [], 0.0
        for item in rng.sample(ITEMS, rng.randint(3, 6)):
            qty = rng.randint(1, 12)
            unit = rng.choice([85.0, 120.0, 240.0, 410.0, 62.5])
            total += qty * unit
            rows.append((item, qty, f"{unit:.2f}", f"{qty * unit:.2f}"))
        return [("h", "Invoice"),
                ("kv", [("Invoice number", f"INV-{rng.randint(10000, 99999)}"), ("Invoice date", date),
                        ("From", VENDOR), ("To", CLIENT), ("Payment terms", "30 days")]),
                ("table", ("Description", "Qty", "Unit price", "Amount"), rows, (0, 0.5, 0.62, 0.82)),
                ("kv", [("Total due", f"{total:.2f}")])]
    if roll < 0.24:
        name, _ = rng.choice(CLAUSES)
        return [("h", f"Amendment No. {rng.randint(1, 6)}"),
                ("kv", [("Amendment date", date), ("Amends", name)]),
                ("p", f"The parties agree to amend the clause titled {name}. " + rng.choice([
                    "The response time for urgent faults is reduced from four hours to three hours.",
                    "The monthly fee increases by four percent from the next contract year.",
                    "Two further sites are added to Schedule A.",
                    "The notice period for termination for convenience is reduced to one hundred and twenty days."])),
                ("p", "All other terms of the agreement remain in force. Signed for both parties.")]
    if roll < 0.36:
        return [("h", "Correspondence"),
                ("kv", [("Date", date), ("From", rng.choice([VENDOR, CLIENT])), ("Subject", rng.choice(
                    ["Missed service level in March", "Request for insurance certificate", "Site access arrangements",
                     "Disputed invoice"]))]),
                ("p", rng.choice([
                    "We write about two urgent faults that were attended after the agreed response time. "
                    "We ask that the service credit is applied to the next invoice.",
                    "Please send the current public liability certificate, which our records show expired last month.",
                    "We dispute the charge for the emergency call out, which was caused by an earlier incomplete repair."])),
                ("p", "Please reply within ten business days.")]
    if roll < 0.46:
        rows = [(f"Site {chr(65 + k)}", rng.choice(["Office", "Warehouse", "Depot", "Workshop"]),
                 f"{rng.randint(800, 9000)} m2", f"{rng.randint(1200, 9800)}.00") for k in range(rng.randint(4, 8))]
        return [("h", rng.choice(["Schedule A: Sites", "Schedule B: Fees"])),
                ("table", ("Site", "Type", "Floor area", "Monthly fee"), rows, (0, 0.25, 0.5, 0.75)),
                ("p", "Fees are reviewed each contract year in line with the published index.")]
    picks = rng.sample(CLAUSES, 3)
    blocks: list[tuple] = [("h", f"Agreement Terms, Section {i}")]
    for k, (name, text) in enumerate(picks):
        blocks.append(("p", f"{i}.{k + 1} {name}. {text}"))
    return blocks


def build_document(kind: str, pages: int, seed: int = 42) -> tuple[str, bytes]:
    name = "Patient record.pdf" if kind == "medical" else "Vendor contract file.pdf"
    fn = patient_page if kind == "medical" else contract_page
    images = []
    for i in range(pages):
        rng = random.Random(f"{seed}:{kind}:{i}")
        images.append(render_page(rng, name, i + 1, fn(rng, i, pages)))
    return name, to_pdf(images)


# ---------------------------------------------------------------- short fictional documents (several per flow)

def _meds_doc(stage: str) -> list[list[tuple]]:
    """Two medication lists for the same fictional patient. They differ on purpose: one dose changed,
    one medicine stopped, one started, and one has a different frequency."""
    adm = stage == "admission"
    regular = [
        ("Metformin", "500 mg", "twice daily", "Type 2 diabetes"),
        ("Lisinopril", "10 mg" if adm else "20 mg", "once daily", "Hypertension"),
        ("Atorvastatin", "20 mg", "once daily at night", "Cholesterol"),
        ("Ferrous sulfate", "200 mg", "once daily" if adm else "twice daily", "Iron deficiency anemia"),
    ]
    if adm:
        regular.append(("Ibuprofen", "400 mg", "three times daily", "Lower back pain"))
    else:
        regular.append(("Paracetamol", "1 g", "four times daily", "Lower back pain"))
        regular.append(("Omeprazole", "20 mg", "once daily", "Stomach protection"))
    page1 = [("h", "Medication List on Admission" if adm else "Medication List on Discharge"),
             ("kv", [("Patient", PATIENT), ("Record number", "TEST-000417"),
                     ("Date", "2024-03-04" if adm else "2024-03-11"), ("Ward", "Example Ward 6"),
                     ("Recorded by", CLINICIANS[3] if adm else CLINICIANS[1])]),
             ("h", "Regular medicines"),
             ("table", ("Medicine", "Dose", "Frequency", "Reason"), regular, (0, 0.3, 0.45, 0.72))]
    page2 = [("h", "As needed medicines and notes"),
             ("table", ("Medicine", "Dose", "Frequency", "Reason"),
              [("Salbutamol inhaler", "100 mcg", "two puffs as needed", "Seasonal asthma")]
              + ([] if adm else [("Senna", "7.5 mg", "at night as needed", "Constipation")]), (0, 0.3, 0.45, 0.72)),
             ("kv", [("Allergies", "Penicillin (rash)")]),
             ("p", "Source of this list: the patient, the community pharmacy record and the medicines brought in."
                   if adm else
                   "Changes made during the stay: ibuprofen stopped because of stomach irritation and replaced with "
                   "paracetamol; omeprazole started; lisinopril increased after repeated high blood pressure readings."),
             ("p", "The patient manages their own medicines at home." if adm else
                   "Follow up with the family doctor in two weeks to review blood pressure and iron levels.")]
    return [page1, page2]


def _trade_doc(kind: str) -> list[list[tuple]]:
    """A purchase order, a delivery note and an invoice for one fictional order. The invoice differs from
    the other two on purpose: one quantity, one unit price, and one line that was never ordered."""
    po_no, dn_no, inv_no = "PO-TEST-2291", "DN-TEST-5104", "INV-TEST-8830"
    ordered = [("Office chair, model A", 12, 85.00), ("Standing desk frame", 6, 240.00),
               ("Monitor arm, dual", 10, 62.50), ("Cable tray, 1.2 m", 20, 14.00)]
    delivered = {"Office chair, model A": 12, "Standing desk frame": 5, "Monitor arm, dual": 10, "Cable tray, 1.2 m": 20}
    if kind == "po":
        rows = [(d, q, f"{u:.2f}", f"{q * u:.2f}") for d, q, u in ordered]
        return [[("h", "Purchase Order"),
                 ("kv", [("Order number", po_no), ("Order date", "2024-05-02"), ("Buyer", CLIENT), ("Supplier", VENDOR),
                         ("Deliver to", "Depot B, Example Industrial Park")]),
                 ("table", ("Description", "Qty", "Unit price", "Amount"), rows, (0, 0.5, 0.62, 0.82)),
                 ("kv", [("Order total", f"{sum(q * u for _, q, u in ordered):.2f}")])],
                [("h", "Order Terms"),
                 ("p", "Prices are fixed for this order. No substitution of items without written agreement from the buyer."),
                 ("p", "Delivery is included in the unit prices. No separate delivery or handling charge applies."),
                 ("p", "Payment terms are 30 days from the invoice date. Invoices must quote the order number."),
                 ("p", "Part deliveries are accepted. Only goods received are payable.")]]
    if kind == "delivery":
        rows = [(d, q, delivered[d], "Back order" if delivered[d] < q else "Complete") for d, q, _ in ordered]
        return [[("h", "Delivery Note"),
                 ("kv", [("Delivery note", dn_no), ("Delivery date", "2024-05-14"), ("Order number", po_no),
                         ("From", VENDOR), ("To", CLIENT), ("Site", "Depot B, Example Industrial Park")]),
                 ("table", ("Description", "Ordered", "Delivered", "Status"), rows, (0, 0.5, 0.64, 0.8))],
                [("h", "Receipt"),
                 ("p", "Goods received and counted at the site. One standing desk frame was not on the vehicle "
                       "and is on back order. All other items were received in good condition."),
                 ("kv", [("Received by", "R. Sampleton"), ("Received on", "2024-05-14"), ("Packages", "9")])]]
    billed = [("Office chair, model A", 12, 85.00), ("Standing desk frame", 6, 240.00),
              ("Monitor arm, dual", 10, 68.50), ("Cable tray, 1.2 m", 20, 14.00)]
    rows = [(d, q, f"{u:.2f}", f"{q * u:.2f}") for d, q, u in billed]
    sub = sum(q * u for _, q, u in billed)
    return [[("h", "Invoice"),
             ("kv", [("Invoice number", inv_no), ("Invoice date", "2024-05-16"), ("Order number", po_no),
                     ("From", VENDOR), ("To", CLIENT), ("Payment terms", "30 days")]),
             ("table", ("Description", "Qty", "Unit price", "Amount"), rows, (0, 0.5, 0.62, 0.82))],
            [("h", "Invoice, continued"),
             ("table", ("Description", "Qty", "Unit price", "Amount"),
              [("Delivery and handling", 1, "45.00", "45.00")], (0, 0.5, 0.62, 0.82)),
             ("kv", [("Subtotal", f"{sub + 45:.2f}"), ("Tax", "0.00"), ("Total due", f"{sub + 45:.2f}")]),
             ("p", "Please pay within 30 days of the invoice date, quoting the invoice number.")],
            [("h", "Remittance Advice"),
             ("kv", [("Invoice number", inv_no), ("Total due", f"{sub + 45:.2f}"), ("Due date", "2024-06-15")]),
             ("p", "Return this page with your payment. Questions about this invoice go to the accounts team "
                   "of the supplier named above.")]]


# document id -> (file name, pages as block lists)
SHORT_DOCS: dict[str, tuple[str, Any]] = {
    "doc_sample_meds_admission": ("Medication list, admission.pdf", lambda: _meds_doc("admission")),
    "doc_sample_meds_discharge": ("Medication list, discharge.pdf", lambda: _meds_doc("discharge")),
    "doc_sample_trade_po": ("Purchase order.pdf", lambda: _trade_doc("po")),
    "doc_sample_trade_delivery": ("Delivery note.pdf", lambda: _trade_doc("delivery")),
    "doc_sample_trade_invoice": ("Invoice.pdf", lambda: _trade_doc("invoice")),
}


def blocks_to_text(pages: list[list[tuple]]) -> str:
    """The same content as plain text, one form feed between pages (what a system export looks like)."""
    out = []
    for blocks in pages:
        lines: list[str] = []
        for b in blocks:
            if b[0] == "h":
                lines += [str(b[1]).upper(), ""]
            elif b[0] == "kv":
                lines += [f"{k}: {v}" for k, v in b[1]] + [""]
            elif b[0] == "table":
                lines.append(" | ".join(str(c) for c in b[1]))
                lines += [" | ".join(str(c) for c in row) for row in b[2]]
                lines.append("")
            elif len(b) > 1 and isinstance(b[1], str):
                lines += [b[1], ""]
        lines.append(FOOTER)
        out.append("\n".join(lines))
    return "\f".join(out)


# The same fictional order in other file types, to try images and text files as sources.
OTHER_DOCS: dict[str, tuple[str, str, str]] = {
    "doc_sample_trade_po_text": ("Purchase order (text export).txt", "text", "doc_sample_trade_po"),
    "doc_sample_trade_delivery_image": ("Delivery note, page 1 (scan).png", "image", "doc_sample_trade_delivery"),
}


def build_other_document(doc_id: str, seed: int = 42) -> tuple[str, bytes]:
    name, kind, base = OTHER_DOCS[doc_id]
    base_name, pages = SHORT_DOCS[base]
    if kind == "text":
        return name, blocks_to_text(pages()).encode("utf-8")
    img = render_page(random.Random(f"{seed}:{base}:0"), base_name, 1, pages()[0])
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return name, buf.getvalue()


def build_short_document(doc_id: str, seed: int = 42) -> tuple[str, bytes]:
    name, pages = SHORT_DOCS[doc_id]
    images = [render_page(random.Random(f"{seed}:{doc_id}:{i}"), name, i + 1, blocks) for i, blocks in enumerate(pages())]
    return name, to_pdf(images)


# ---------------------------------------------------------------- sample flows

SUMMARIZE_SYSTEM = """You are a clinical documentation analyst preparing material for a reviewer who must understand a long patient record quickly and accurately. You are given a small group of consecutive pages from the record. Other analysts receive the neighbouring pages, and a later step combines every group's notes into one summary, so your notes must stand on their own and must not assume anything you were not shown.

How to read the pages
- The pages are scans. Read every page fully, including tables, headers, stamps and handwritten additions where legible.
- A group may mix page types: progress notes, laboratory reports, medication lists, imaging reports, referral letters, discharge summaries.
- A page can be shared with the neighbouring group. Report what is on it anyway. The combining step removes repeats.
- If part of a page cannot be read, say so and name the page. Do not guess at illegible values.

What to capture
- Problems and diagnoses: each condition mentioned, its status (new, stable, improving, worsening, resolved) and the date it was recorded.
- Medication: every medicine named, with dose and frequency, and any start, stop or change, with the stated reason.
- Results: laboratory values that are outside their reference range or that changed meaningfully, with value, unit and date. Imaging findings and impressions.
- Events: admissions, discharges, procedures, referrals and their outcomes.
- Plans and follow up: what was planned, by whom, and by when. Note where a plan appears not to have been carried out on the pages you can see.
- Anything that looks inconsistent, such as a medicine listed at two different doses, or a result that contradicts a note.

What to leave out
- Administrative text that carries no clinical meaning (letterheads, page footers, routine disclaimers).
- Your own medical opinion. Report what the record says. Do not diagnose, advise or speculate about causes.
- Normal results, unless the record itself draws attention to them.

Notes on each page type
- Progress note: capture the reason for the visit, the measurements that were taken (blood pressure, pulse, weight), the assessment in the clinician's words and the plan. A note that only repeats an earlier note still counts: record the date and that nothing changed.
- Laboratory report: record the collection date, then each flagged result with its value, unit and reference range. Mention unflagged results only when a note elsewhere in your pages refers to them.
- Medication list: record the full list as it stands on that date. Lists are snapshots, so two lists on different dates may differ, and the difference is itself a finding.
- Imaging report: record the study, the body area, the findings in one sentence and the impression as written.
- Referral letter: record who referred to whom, for what, and what question was asked.
- Discharge summary: record the admission date, the reason, the length of stay, the course and the discharge plan.
- A page that fits none of these: describe in one sentence what it is and what it adds.

Handling uncertainty
- When a date is missing, say that the page is undated. Do not borrow a date from a neighbouring page.
- When two pages disagree, record both statements with their pages. Do not choose between them.
- When a value has no unit on the page, write the value and say that no unit was given.
- When handwriting changes a printed value, record both and say which is handwritten.
- When a page is blank or holds only a header, say so in one line.

How to write
- Use short, plain statements. One fact per statement.
- Give dates in the form they appear in the record.
- Keep numbers exact, with their units.
- Group your notes under these headings, and omit a heading when you have nothing for it: Problems, Medication, Results, Events, Plans and follow up, Inconsistencies.
- Be complete but brief. A typical group of four pages needs between 150 and 400 words."""


QUALITY_CHECKLIST = """

Before you finish, check your notes against this list
- Every statement can be traced to a page you were shown, and you could point to the line it came from.
- Every number has its unit, and every number matches the page character for character.
- Every date is written the way the page writes it.
- Nothing is reported twice within your notes.
- Nothing is softened or strengthened: "not at target" stays "not at target", it does not become "poorly controlled".
- Abbreviations are kept as written unless the page itself spells them out.
- Names of people and organisations are spelled as on the page.
- You have not carried over anything from general knowledge. If the page does not say it, it is not in your notes.
- You have said plainly where a page was unreadable, blank or out of order.
- The headings you used are from the list above, in the order given, and empty headings are left out.

Example of the expected style
Results
- 2023-01-16: Glucose, fasting 108 mg/dL, reference 70-99, flagged high.
- 2023-01-16: TSH 4.2 mIU/L, reference 0.4-4.0, flagged high.
Plans and follow up
- 2023-01-16: repeat blood tests before the next visit (Dr. R. Testwell).
The example shows the form only. Never copy its content into your notes."""

SUMMARIZE_SYSTEM += QUALITY_CHECKLIST

SUMMARIZE_INSTR = "Write notes on the pages you were given, under the headings listed above."

FINAL_SYSTEM = """You are combining notes on consecutive page groups of one patient record into a single summary for a reviewer. Each set of notes is tagged with the pages it covers. Neighbouring groups overlap by one page, so the same fact can appear twice. Report it once.

Write the summary under these headings: Overview, Problems, Medication, Key results, Events, Open follow up, Inconsistencies. Under Overview give three to five sentences that a reviewer could read alone. Order the content of each other section by date. Where the notes disagree, say so under Inconsistencies and cite both places. Do not add facts that are not in the notes, and do not give medical advice.

Every finding must cite the document pages it comes from, using the page numbers on the notes it came from."""

FINAL_INSTR = "Group findings by problem, medication and follow up. Keep it under 900 words."

CLASSIFY_SYSTEM = """You classify single pages of a scanned record by type. Read the whole page, then choose the one type that best describes it. Use the page's title and layout first, and its content second. A page with a table of test names, results, units and reference ranges is a lab report. A page listing medicines with doses is a medication list. If nothing fits, choose other."""

CLASSIFY_INSTR = "Classify this page."

EXTRACT_SYSTEM = """You extract laboratory results from one page of a scanned record. Copy each row of the results table exactly: the test name, the result as printed, the unit, the reference range and the flag (H, L or empty). Do not convert units, round values or skip rows. If a cell cannot be read, write unreadable for that cell. Also give the collection date printed on the page."""

EXTRACT_INSTR = "Extract every result on this page."

CONTRACT_SUM_SYSTEM = SUMMARIZE_SYSTEM.replace(
    "clinical documentation analyst", "contracts analyst").replace("patient record", "contract file").replace(
    "progress notes, laboratory reports, medication lists, imaging reports, referral letters, discharge summaries",
    "agreement terms, amendments, schedules, invoices and letters").split("What to capture")[0] + """What to capture
- Obligations: who must do what, by when, and what follows if they do not.
- Money: fees, payment terms, interest, credits and any change to them, with amounts and dates.
- Dates: effective dates, renewal dates, notice periods and deadlines.
- Changes: each amendment, the clause it changes and the new wording in plain terms.
- Disputes and open issues raised in letters, and whether the file shows them resolved.
- Anything inconsistent, such as an invoice that does not match the fee schedule.

Notes on each page type
- Agreement terms: record each clause by its title and number, and state the obligation in one sentence. Quote figures, periods and percentages exactly.
- Amendment: record its number and date, the clause it changes, and the position after the change. An amendment replaces what came before it, so the later one governs.
- Schedule: record what the schedule lists (sites, fees) and its totals. Individual rows matter only when another page refers to them.
- Invoice: record the invoice number, date, total and anything unusual, such as a charge that the agreement does not appear to allow.
- Correspondence: record who wrote to whom, the date, the subject, what was asked and by when.
- A page that fits none of these: describe in one sentence what it is and what it adds.

Handling uncertainty
- When a date is missing, say that the page is undated. Do not borrow a date from a neighbouring page.
- When two pages disagree, record both statements with their pages. Do not choose between them.
- When an amount has no currency on the page, write the amount and say that no currency was given.
- When a page is blank or holds only a header, say so in one line.

How to write
- Use short, plain statements. One fact per statement. Keep amounts and dates exact.
- Group your notes under these headings, and omit a heading when you have nothing for it: Obligations, Money, Dates, Changes, Open issues, Inconsistencies.
- Do not give legal advice. Report what the file says.""" + QUALITY_CHECKLIST.replace(
    "Results\n- 2023-01-16: Glucose, fasting 108 mg/dL, reference 70-99, flagged high.\n- 2023-01-16: TSH 4.2 mIU/L, reference 0.4-4.0, flagged high.\nPlans and follow up\n- 2023-01-16: repeat blood tests before the next visit (Dr. R. Testwell).",
    "Money\n- Monthly fee payable within 30 days of a correct invoice; late amounts carry 1 percent interest per month.\nChanges\n- Amendment No. 2 (2023-06-11): urgent fault response reduced from four hours to three hours.")

CONTRACT_FINAL_SYSTEM = """You are combining notes on consecutive page groups of one contract file into a single brief for a contract manager. Each set of notes is tagged with the pages it covers, and neighbouring groups overlap by one page, so report each fact once.

Write the brief under these headings: Overview, Obligations by party, Money, Key dates, Amendments in order, Open issues, Inconsistencies. State the current position after all amendments, not only the original terms. Do not add facts that are not in the notes and do not give legal advice. Cite the document pages for every point."""


def _node(nid: str, typ: str, x: int, y: int, data: dict) -> dict:
    return {"id": nid, "type": typ, "position": {"x": x, "y": y}, "data": data}


def _edge(eid: str, s: str, t: str, data: dict | None = None) -> dict:
    return {"id": eid, "source": s, "target": t, "data": data or {}}


def medical_flow() -> dict:
    return {"nodes": [
        _node("source", "source", 40, 225, {"title": "Patient record", "kind": "single", "default_document": "doc_sample_medical_150"}),
        _node("summarize", "step", 340, 70, {
            "title": "Summarize window", "system": SUMMARIZE_SYSTEM, "instructions": SUMMARIZE_INSTR, "model": "sonnet",
            # On the real gateway (2026-11-25) Sonnet wrote about 1,370 tokens a window, close to the earlier limit of 1,500.
            "max_tokens": 2500, "expected_output": 1400, "thinking": "off", "output": {"type": "text", "fields": []},
            "track_pages": True}),
        _node("final", "step", 640, 70, {
            "title": "Final summary", "system": FINAL_SYSTEM, "instructions": FINAL_INSTR, "model": "opus",
            "max_tokens": 8000, "expected_output": 4000, "thinking": "off", "output": {"type": "text", "fields": []},
            "track_pages": True}),
        _node("out_summary", "output", 940, 80, {"title": "Summary with citations", "format": "text"}),
        _node("classify", "step", 340, 380, {
            "title": "Classify page", "system": CLASSIFY_SYSTEM, "instructions": CLASSIFY_INSTR, "model": "haiku",
            "max_tokens": 300, "expected_output": 40, "thinking": "off", "track_pages": True,
            "output": {"type": "schema", "fields": [
                {"name": "page_type", "type": "enum", "description": "The type of this page",
                 "values": ["progress note", "lab report", "medication list", "imaging report", "letter",
                            "discharge summary", "other"]}]}}),
        _node("extract", "step", 640, 380, {
            "title": "Extract lab values", "system": EXTRACT_SYSTEM, "instructions": EXTRACT_INSTR, "model": "sonnet",
            "max_tokens": 2000, "expected_output": 500, "thinking": "off", "track_pages": True,
            "output": {"type": "schema", "fields": [
                {"name": "collected", "type": "string", "description": "Collection date as printed"},
                {"name": "results", "type": "table", "description": "One row per test",
                 "columns": ["test", "result", "unit", "reference", "flag"]}]}}),
        _node("out_labs", "output", 940, 390, {"title": "Lab results table", "format": "table"}),
    ], "edges": [
        _edge("e1", "source", "summarize", {"instruction": "map", "window": 4, "overlap": 1}),
        _edge("e2", "summarize", "final", {"instruction": "reduce"}),
        _edge("e3", "final", "out_summary"),
        _edge("e4", "source", "classify", {"instruction": "map", "window": 1, "overlap": 0}),
        _edge("e5", "classify", "extract", {"instruction": "filter",
                                            "rule": {"field": "page_type", "op": "equals", "value": "lab report"}}),
        _edge("e6", "extract", "out_labs"),
    ]}


def contract_flow() -> dict:
    return {"nodes": [
        _node("source", "source", 40, 225, {"title": "Contract file", "kind": "single", "default_document": "doc_sample_contract_60"}),
        _node("notes", "step", 340, 70, {
            "title": "Note the terms", "system": CONTRACT_SUM_SYSTEM, "instructions": "Write notes on the pages you were given.",
            "model": "sonnet", "max_tokens": 1500, "expected_output": 900, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("brief", "step", 640, 70, {
            "title": "Contract brief", "system": CONTRACT_FINAL_SYSTEM, "instructions": "Keep it under 800 words.",
            "model": "sonnet", "max_tokens": 8000, "expected_output": 4000, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("out_brief", "output", 940, 80, {"title": "Brief with citations", "format": "text"}),
        _node("classify", "step", 340, 380, {
            "title": "Classify page", "model": "haiku", "max_tokens": 300, "expected_output": 40, "thinking": "off",
            "system": "You classify single pages of a scanned contract file by type. Read the whole page and choose the "
                      "one type that fits best, using the title and layout first. A page with an invoice number and "
                      "priced line items is an invoice.",
            "instructions": "Classify this page.", "track_pages": True,
            "output": {"type": "schema", "fields": [
                {"name": "page_type", "type": "enum", "description": "The type of this page",
                 "values": ["agreement terms", "amendment", "invoice", "correspondence", "schedule", "other"]}]}}),
        _node("lines", "step", 640, 380, {
            "title": "Extract invoice lines", "model": "sonnet", "max_tokens": 2000, "expected_output": 500,
            "thinking": "off", "track_pages": True,
            "system": "You extract invoice data from one page of a scanned contract file. Copy the invoice number, the "
                      "invoice date and every line item exactly as printed. Do not round amounts or skip rows. "
                      "If a cell cannot be read, write unreadable for that cell.",
            "instructions": "Extract this invoice.",
            "output": {"type": "schema", "fields": [
                {"name": "invoice_number", "type": "string", "description": "As printed"},
                {"name": "invoice_date", "type": "string", "description": "As printed"},
                {"name": "lines", "type": "table", "description": "One row per line item",
                 "columns": ["description", "qty", "unit_price", "amount"]}]}}),
        _node("out_lines", "output", 940, 390, {"title": "Invoice lines table", "format": "table"}),
    ], "edges": [
        _edge("e1", "source", "notes", {"instruction": "map", "window": 3, "overlap": 1}),
        _edge("e2", "notes", "brief", {"instruction": "reduce"}),
        _edge("e3", "brief", "out_brief"),
        _edge("e4", "source", "classify", {"instruction": "map", "window": 1, "overlap": 0}),
        _edge("e5", "classify", "lines", {"instruction": "filter",
                                          "rule": {"field": "page_type", "op": "equals", "value": "invoice"}}),
        _edge("e6", "lines", "out_lines"),
    ]}


COMPARE_SYSTEM = """You compare two medication lists for the same patient: the list recorded on admission and the list issued on discharge. Your reader is a pharmacist who must confirm that every difference between the two lists is intended.

Work through every medicine that appears on either list, regular and as needed. For each one decide which of these applies: unchanged, dose changed, frequency changed, stopped (on the admission list only), or started (on the discharge list only). Compare the name, the dose and the frequency exactly as printed. Do not judge whether a change is clinically right.

Then check whether the discharge list explains each change. A change with no stated reason is an unexplained change and must be listed separately.

Write three short sections: Changes, Unchanged, and Unexplained changes. Use one bullet per medicine. Keep doses and frequencies exactly as printed."""

ORDER_SYSTEM = """You read a purchase order and record what was ordered, so that an invoice can be checked against it later. Copy every line exactly as printed: the description, the quantity, the unit price and the line amount. Then record the order number and any term that affects what may be invoiced, such as fixed prices, delivery charges, part deliveries and payment terms. Do not round amounts or skip lines."""

DELIVERY_SYSTEM = """You read a delivery note and record what was actually delivered, so that an invoice can be checked against it later. Copy every line exactly as printed: the description, the quantity ordered, the quantity delivered and the status. Record the delivery note number, the order number it refers to, and anything the receipt says about missing or damaged goods."""

CHECK_SYSTEM = """You check one page of a supplier invoice against two references: what was ordered (from the purchase order) and what was delivered (from the delivery note). Your reader is an accounts clerk deciding whether the invoice can be paid.

For every charge on this invoice page, state whether it agrees with the references. Report each of these when you find it: a quantity billed that is more than the quantity delivered; a unit price that differs from the order; a charge for something that was not ordered or that the order terms exclude; an order number that does not match. Give the figures from both sides, exactly as printed.

Two settings come with each run. Price tolerance: {{Price tolerance}}. Treat a unit price as agreeing with the order when it differs by no more than this amount, in the currency of the invoice. Accept delivery charges the order did not list: {{Accept delivery charges}}. When this is no, report any such charge; when it is yes, let it pass and say that you did.

If the page holds no charges, say so in one line. Do not repeat charges that agree in detail: one line saying they agree is enough."""

VERDICT_SYSTEM = """You are given the checks made on each page of one supplier invoice. Combine them into a short verdict for an accounts clerk. Start with one line: Pay in full, Pay in part, or Do not pay yet. Then list each discrepancy once, with the figures from the invoice, the order and the delivery note, and the amount it changes the total by. Finish with the amount that is supported by the order and the delivery."""


def compare_flow() -> dict:
    return {"nodes": [
        _node("src_adm", "source", 40, 60, {"title": "Admission list", "kind": "single",
                                            "default_document": "doc_sample_meds_admission"}),
        _node("src_dis", "source", 40, 300, {"title": "Discharge list", "kind": "single",
                                             "default_document": "doc_sample_meds_discharge"}),
        _node("compare", "step", 380, 170, {
            "title": "Compare the lists", "system": COMPARE_SYSTEM,
            "instructions": "Compare the two medication lists.",
            "model": "sonnet", "max_tokens": 3000, "expected_output": 900, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("out_compare", "output", 720, 180, {"title": "Differences with citations", "format": "text"}),
    ], "edges": [
        _edge("e1", "src_adm", "compare", {"instruction": "reduce"}),
        _edge("e2", "src_dis", "compare", {"role": "reference"}),
        _edge("e3", "compare", "out_compare"),
    ]}


def three_way_flow() -> dict:
    return {"nodes": [
        _node("src_po", "source", 40, 40, {"title": "Purchase order", "kind": "single",
                                           "default_document": "doc_sample_trade_po"}),
        _node("src_dn", "source", 40, 220, {"title": "Delivery note", "kind": "single",
                                            "default_document": "doc_sample_trade_delivery"}),
        _node("src_inv", "source", 40, 420, {"title": "Invoice", "kind": "single",
                                             "default_document": "doc_sample_trade_invoice"}),
        _node("order", "step", 350, 40, {
            "title": "Read the order", "system": ORDER_SYSTEM, "instructions": "Record what was ordered.",
            "model": "haiku", "max_tokens": 1500, "expected_output": 500, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("delivery", "step", 350, 220, {
            "title": "Read the delivery", "system": DELIVERY_SYSTEM, "instructions": "Record what was delivered.",
            "model": "haiku", "max_tokens": 1500, "expected_output": 400, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("check", "step", 670, 420, {
            "title": "Check the invoice", "system": CHECK_SYSTEM, "instructions": "Check this invoice page.",
            "model": "sonnet", "max_tokens": 2000, "expected_output": 500, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("verdict", "step", 990, 420, {
            "title": "Verdict", "system": VERDICT_SYSTEM, "instructions": "Write the verdict.",
            "model": "sonnet", "max_tokens": 2500, "expected_output": 700, "thinking": "off",
            "output": {"type": "text", "fields": []}, "track_pages": True}),
        _node("out_verdict", "output", 1310, 430, {"title": "Invoice verdict", "format": "text"}),
    ], "edges": [
        _edge("e1", "src_po", "order", {"instruction": "reduce"}),
        _edge("e2", "src_dn", "delivery", {"instruction": "reduce"}),
        _edge("e3", "src_inv", "check", {"instruction": "map", "window": 1, "overlap": 0}),
        _edge("e4", "order", "check", {"role": "reference"}),
        _edge("e5", "delivery", "check", {"role": "reference"}),
        _edge("e6", "check", "verdict", {"instruction": "reduce"}),
        _edge("e7", "verdict", "out_verdict"),
    ], "inputs": [
        {"name": "Price tolerance", "type": "number", "default": 0.5,
         "description": "Largest unit price difference that still counts as agreeing with the order"},
        {"name": "Accept delivery charges", "type": "yesno", "default": False,
         "description": "Let a delivery charge pass when the order did not list one"},
    ]}


SAMPLE_FLOWS = [
    ("flow_sample_medical", "Medical record summary",
     "Summarizes a long record with page citations, and pulls lab results into a table.", medical_flow),
    ("flow_sample_contract", "Contract file review",
     "Briefs a contract file with page citations, and pulls invoice lines into a table.", contract_flow),
    ("flow_sample_compare", "Compare two medication lists",
     "Two documents in one call: what changed between the admission list and the discharge list.", compare_flow),
    ("flow_sample_three_way", "Check an invoice against its order",
     "Three documents: reads the order and the delivery note, then checks each invoice page against both.",
     three_way_flow),
]
SAMPLE_DOCS = [("medical", 150), ("medical", 24), ("contract", 60)]


async def install_samples(db: Db, cfg: Section, force: bool = False) -> dict:
    """Creates the sample flows and documents if they are missing. Safe to run again."""
    made = {"flows": 0, "documents": 0}
    for flow_id, name, desc, fn in SAMPLE_FLOWS:
        row = await db.fetchone("SELECT flow_id FROM flows WHERE flow_id = %s", (flow_id,))
        if row and not force:
            continue
        graph = fn()
        await db.execute(
            # Published from the start, so the public endpoint has something to call on a fresh install.
            """INSERT INTO flows (flow_id, name, description, graph, version, published_version, is_sample)
               VALUES (%s,%s,%s,%s,1,1,true)
               ON CONFLICT (flow_id) DO UPDATE SET name = excluded.name, description = excluded.description,
                   graph = excluded.graph, updated_at = now()""", (flow_id, name, desc, Jsonb(graph)))
        await db.execute(
            "INSERT INTO flow_versions (flow_id, version, name, graph) VALUES (%s,1,%s,%s) "
            "ON CONFLICT (flow_id, version) DO UPDATE SET graph = excluded.graph", (flow_id, name, Jsonb(graph)))
        made["flows"] += 1
    for kind, pages in SAMPLE_DOCS:
        base = "Patient record" if kind == "medical" else "Vendor contract file"
        name = f"{base}.pdf" if pages >= 60 else f"{base} (short, {pages} pages).pdf"
        doc_id = f"doc_sample_{kind}_{pages}"
        row = await db.fetchone("SELECT document_id FROM documents WHERE document_id = %s", (doc_id,))
        if row and not force:
            continue
        _, pdf = build_document(kind, pages)
        await store_document(db, name, pdf, is_sample=True, document_id=doc_id)
        made["documents"] += 1
    for doc_id in SHORT_DOCS:
        row = await db.fetchone("SELECT document_id FROM documents WHERE document_id = %s", (doc_id,))
        if row and not force:
            continue
        name, pdf = build_short_document(doc_id)
        await store_document(db, name, pdf, is_sample=True, document_id=doc_id)
        made["documents"] += 1
    for doc_id in OTHER_DOCS:
        row = await db.fetchone("SELECT document_id FROM documents WHERE document_id = %s", (doc_id,))
        if row and not force:
            continue
        name, data = build_other_document(doc_id)
        await store_document(db, name, data, is_sample=True, document_id=doc_id, cfg=cfg)
        made["documents"] += 1
    return made
