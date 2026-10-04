"""Generate the fake finance workspace for the Trace demo (Harbour Lane Trading Ltd).

Run:
    uv run --with openpyxl --with fpdf2 --with pymupdf python scripts/generate_workspace.py

Deterministic (fixed seed, fixed timestamps). Wipes and rebuilds workspace/, including its own git
history with backdated commits. That history lives in workspace/.trace/git (not workspace/.git) so the
outer repo can track the workspace files and its history as plain files. Use it with:
    git --git-dir=workspace/.trace/git log      (core.worktree points back at workspace/) Inbox invoices, the 2027 lease and the two newest emails stay
untracked (they are the demo). ground_truth/ is git-ignored inside the workspace.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import zipfile
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTPUTF8
from pathlib import Path

import pymupdf as fitz
from faker import Faker
from fontTools.ttLib import TTCollection
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "workspace"
GIT_DIR = WS / ".trace" / "git"
SEED = 20261005
rng = random.Random(SEED)
fake = Faker("en_GB")
fake.seed_instance(SEED)
TODAY = date(2026, 10, 5)
CLOSE = date(2026, 9, 30)
D = date

# ----------------------------------------------------------------------------- master data
CO = dict(
    name_en="Harbour Lane Trading Ltd", name_zh="海港貿易有限公司", br="63817254",
    addr_en="Room 1203, 12/F, Wing Tat Commercial Centre, 88 Hoi Bun Road, Kwun Tong, Kowloon, Hong Kong",
    addr_zh="香港九龍觀塘海濱道88號永達商業中心12樓1203室",
    warehouse="Unit 9A, 9/F, Oceanic Godown Centre, 21 Sheung Yuet Road, Kowloon Bay, Kowloon",
    bank="Victoria Harbour Bank Limited", bank_acct="088-412-09375-1", domain="harbourlane.com.hk",
)
PEOPLE = {"anna": ("Anna Chan", "anna.chan@harbourlane.com.hk", "Finance Manager"),
          "ken": ("Ken Lau", "ken.lau@harbourlane.com.hk", "Accounts Clerk"),
          "david": ("David Wong", "david.wong@harbourlane.com.hk", "Director / Owner")}

SUP = {
    "S01": dict(name_en="Shenzhen Parts Co., Ltd.", name_zh="深圳市零件有限公司", currency="RMB", terms=60,
                domain="shenzhenparts.com", email="accounts@shenzhenparts.com", account="310",
                bank="Pearl River Commercial Bank, Shenzhen Futian Branch (珠江商贸银行深圳福田支行)",
                bank_acct="6214 8320 0019 2049", reg="USCC 91440300MA5G7K2X3R", tel="+86 755 2861 4402",
                addr_zh="深圳市宝安区福永街道永福路128号3栋5楼", addr_en="5/F, Bldg 3, 128 Yongfu Road, Fuyong, Bao'an, Shenzhen",
                contract="docs/contracts/S01_supply_agreement_2026.pdf", contract_no="HL-SP-2026-01"),
    "S02": dict(name_en="Dongguan Precision Electronics Co., Ltd.", name_zh="东莞精密电子有限公司", currency="USD",
                terms=30, domain="dg-precision.cn", email="ar@dg-precision.cn", account="310",
                bank="Greater Bay Trust Bank, Dongguan Branch (SWIFT GBTBCNDGXXX)", bank_acct="7800 1123 4588 0062",
                reg="USCC 91441900MA4WQ8L52C", tel="+86 769 8533 7120",
                addr_zh="东莞市长安镇振安中路66号", addr_en="66 Zhen'an Middle Road, Chang'an Town, Dongguan, Guangdong",
                contract="docs/contracts/S02_supply_agreement_2026.pdf", contract_no="HL-DPE-2026-01"),
    "S03": dict(name_en="Pacific Freight Logistics Ltd", name_zh="", currency="HKD", terms=30,
                domain="pacfreight.com.hk", email="billing@pacfreight.com.hk", account="425",
                bank="Victoria Harbour Bank Limited", bank_acct="088-221-55190-3", reg="BR No. 50993312",
                tel="+852 2418 6630", addr_en="Unit 1608, Kwai Fong Logistics Tower, 38 Kwai Hei Street, Kwai Chung, N.T.",
                contract="docs/contracts/S03_freight_rate_card_2026.pdf"),
    "S04": dict(name_en="Kowloon Bay Properties Ltd", name_zh="九龍灣置業有限公司", currency="HKD", terms=7,
                domain="kbproperties.com.hk", email="leasing@kbproperties.com.hk", account="469",
                bank="Lion Rock Bank Limited", bank_acct="512-339-80417-0", reg="BR No. 21874460", tel="+852 2795 3100",
                addr_en="28/F, KBP Tower, 9 Wang Chiu Road, Kowloon Bay, Kowloon",
                contract="docs/contracts/S04_lease_2024_2026.pdf"),
    "S05": dict(name_en="CloudDesk Inc.", name_zh="", currency="USD", terms=15, domain="clouddesk.io",
                email="billing@clouddesk.io", account="485", bank="Sierra Mesa Bank (SWIFT SMBKUS6L)",
                bank_acct="4410-0928-1173", reg="EIN 84-3920117", tel="+1 408 555 0142",
                addr_en="1200 Larkin Avenue, Suite 300, Sunnyvale, CA 94086, USA",
                contract="docs/contracts/S05_clouddesk_order_form.pdf"),
}
FAKE_DOMAIN, NEW_BANK = "shenzhen-parts.co", ("Nanhai Union Bank, Shenzhen Bao'an Branch (南海联合银行深圳宝安支行)", "6230 5821 4407 7731")

PRICES = {  # contract price schedules (S01 §4.2 / S02 §4.2)
    "S01": {"SP-4410": ("Power management IC module", "电源管理模块", "pc", 109.00),
            "SP-2208": ("USB-C connector assembly", "USB-C连接器组件", "pc", 23.50),
            "SP-3315": ("Relay module 12V", "继电器模块 12V", "pc", 46.80),
            "SP-1102": ("MLCC capacitor reel (5,000 pcs)", "陶瓷电容卷盘（5000只）", "reel", 312.00)},
    "S02": {"DPE-PCB6": ("6-layer PCB assembly", "六层PCB组装", "pc", 14.20),
            "DPE-ENC1": ("Aluminium enclosure", "铝合金外壳", "pc", 6.85),
            "DPE-CBL12": ("Wire harness 12-pin", "12针线束", "pc", 2.40)},
}
FREIGHT = {"TRK-20": ("Cross-border trucking Shenzhen - Kowloon Bay, 20ft", "container", 3850),
           "TRK-40": ("Cross-border trucking Shenzhen - Kowloon Bay, 40ft", "container", 5200),
           "CUS": ("Import declaration & customs clearance", "shipment", 680),
           "WH": ("Warehouse handling (in/out)", "pallet", 45),
           "PSS": ("Peak season surcharge (1 Aug - 31 Oct)", "container", 900)}

FX = {"2025-11": (7.79, 1.074), "2025-12": (7.78, 1.071), "2026-01": (7.79, 1.072), "2026-02": (7.81, 1.077),
      "2026-03": (7.82, 1.079), "2026-04": (7.80, 1.076), "2026-05": (7.79, 1.073), "2026-06": (7.81, 1.078),
      "2026-07": (7.82, 1.083), "2026-08": (7.81, 1.082), "2026-09": (7.80, 1.080), "2026-10": (7.80, 1.080)}

ACCOUNTS = [  # code, name, type, group
    ("090", "Victoria Harbour Bank - HKD Current", "Bank", "Balance sheet"),
    ("610", "Accounts Receivable", "Current Asset", "Balance sheet"),
    ("620", "Prepayments", "Current Asset", "Balance sheet"),
    ("630", "Inventory", "Inventory", "Balance sheet"),
    ("710", "Office & Warehouse Equipment", "Fixed Asset", "Balance sheet"),
    ("711", "Less Accumulated Depreciation", "Fixed Asset", "Balance sheet"),
    ("800", "Accounts Payable", "Current Liability", "Balance sheet"),
    ("820", "Accrued Liabilities", "Current Liability", "Balance sheet"),
    ("825", "MPF Payable", "Current Liability", "Balance sheet"),
    ("960", "Retained Earnings", "Equity", "Balance sheet"),
    ("970", "Share Capital", "Equity", "Balance sheet"),
    ("200", "Sales", "Revenue", "Revenue"),
    ("260", "Other Revenue", "Revenue", "Revenue"),
    ("270", "Interest Income", "Revenue", "Revenue"),
    ("310", "Cost of Goods Sold", "Direct Costs", "Cost of sales"),
    ("425", "Freight & Courier", "Expense", "Freight & logistics"),
    ("445", "Utilities - Electricity", "Expense", "Facilities"),
    ("469", "Rent", "Expense", "Facilities"),
    ("471", "Building Management Fees", "Expense", "Facilities"),
    ("473", "Repairs & Maintenance", "Expense", "Facilities"),
    ("477", "Salaries", "Expense", "Staff"),
    ("478", "MPF Contributions", "Expense", "Staff"),
    ("404", "Bank Fees", "Expense", "Admin"),
    ("412", "Consulting & Accounting", "Expense", "Admin"),
    ("429", "General Expenses", "Expense", "Admin"),
    ("433", "Insurance", "Expense", "Admin"),
    ("485", "Software Subscriptions", "Expense", "Admin"),
    ("489", "Telephone & Internet", "Expense", "Admin"),
    ("493", "Travel - Local & Cross-border", "Expense", "Admin"),
    ("497", "Foreign Exchange Gain/Loss", "Expense", "Admin"),
]
ACC = {a[0]: a for a in ACCOUNTS}
PL_CODES = [a[0] for a in ACCOUNTS if a[3] != "Balance sheet"]
BUDGET = {"200": 1_350_000, "260": 0, "270": 1_500, "310": 600_000, "425": 18_000, "445": 4_800, "469": 80_000,
          "471": 6_800, "473": 2_000, "477": 432_000, "478": 26_400, "404": 450, "429": 2_500, "485": 12_700,
          "489": 1_900, "493": 4_000, "497": 0}
BUDGET_ONE_OFF = {("433", 1): 28_800, ("412", 3): 45_000}


def budget(code, m):
    return BUDGET.get(code, 0) + BUDGET_ONE_OFF.get((code, m), 0)


# ----------------------------------------------------------------------------- helpers
def bday(d):
    while d.weekday() >= 5:
        d += timedelta(1)
    return d


def ym(d):
    return d.strftime("%Y-%m")


def fx(cur, d):
    return 1.0 if cur == "HKD" else FX[ym(d)][0 if cur == "USD" else 1]


def r2(x):
    return round(x + 1e-9, 2)


def money(x):
    return f"{x:,.2f}"


def months(a, b):
    y, m = a
    while (y, m) <= b:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y, m):
    return (D(y + (m == 12), m % 12 + 1, 1) - timedelta(1))


def last_bday(y, m):
    d = month_end(y, m)
    while d.weekday() >= 5:
        d -= timedelta(1)
    return d


def split2(s, n):
    """Greedy-wrap an address at ', ' boundaries into lines of at most ~n chars."""
    lines = [""]
    for part in s.split(", "):
        if lines[-1] and len(lines[-1]) + len(part) + 2 > n:
            lines.append("")
        lines[-1] += (", " if lines[-1] else "") + part
    return [x + ("," if i < len(lines) - 1 else "") for i, x in enumerate(lines)]


def zh_date(d):
    return f"{d.year}年{d.month}月{d.day}日"


def en_date(d):
    return f"{d.day} {d:%b %Y}"


# ----------------------------------------------------------------------------- supplier invoices
INVOICES: list[dict] = []


def mk_inv(sid, no, d, lines, file, folder, bank=None, email=None):
    s = SUP[sid]
    sub = r2(sum(r2(q * u) for _, _, q, u in lines))
    inv = dict(sid=sid, no=no, date=d, due=d + timedelta(s["terms"]), currency=s["currency"], lines=lines,
               subtotal=sub, tax=0.0, total=sub, account=s["account"], bank=bank or s["bank_acct"],
               bank_name=s["bank"] if bank is None else NEW_BANK[0], email=email or s["email"],
               file=file, folder=folder)
    inv["pay_date"] = bday(inv["due"])
    INVOICES.append(inv)
    return inv


def folder_of(d):
    return f"docs/invoices/{ym(d)}" if d >= D(2026, 7, 1) else None


def s01_lines(qa, qb, extra=()):
    p = PRICES["S01"]
    out = [("SP-4410", p["SP-4410"][1], qa, p["SP-4410"][3]), ("SP-2208", p["SP-2208"][1], qb, p["SP-2208"][3])]
    return out + [(c, p[c][1], q, p[c][3]) for c, q in extra]


def s02_lines(a, b, c):
    p = PRICES["S02"]
    return [(k, f"{p[k][0]} / {p[k][1]}", q, p[k][3]) for k, q in zip(p, (a, b, c))]


def s03_lines(n20, n40, pallets, peak):
    q = {"TRK-20": n20, "TRK-40": n40, "CUS": n20 + n40, "WH": pallets, "PSS": (n20 + n40) if peak else 0}
    return [(k, FREIGHT[k][0], q[k], FREIGHT[k][2]) for k in FREIGHT if q[k]]


S03_NO = {7: 2204, 8: 2247, 9: 2291}
for y, m in months((2025, 11), (2026, 9)):
    k = (y - 2026) * 12 + m - 7  # months relative to Jul 2026
    # S01 monthly, ~8th
    d = bday(D(y, m, 8))
    no = f"SP-{y}-{640 + 25 * m + m % 3:04d}" if y == 2026 else f"SP-2025-{1010 + 25 * m:04d}"
    extra = [("SP-3315", rng.choice([600, 800, 1000]))] + ([("SP-1102", rng.choice([10, 15, 20]))] if m % 2 else [])
    mk_inv("S01", no, d, s01_lines(rng.choice([1600, 1800, 2000, 2200]), rng.choice([2500, 3000, 3500]), extra),
           f"INV-{no}.pdf", folder_of(d))
    # S02 monthly, ~15th
    d = bday(D(y, m, 15))
    no = f"DPE/INV/{361 + 9 * k:04d}"
    mk_inv("S02", no, d, s02_lines(rng.choice([1200, 1500, 1800]), rng.choice([800, 1000, 1200]),
                                   rng.choice([2000, 3000, 4000])), no.replace("/", "-") + ".pdf", folder_of(d))
    # S03 monthly freight
    d = bday(D(y, m, 1 if (y, m) == (2026, 9) else 3))
    no = f"INV-{S03_NO.get(m) if y == 2026 and m >= 7 else 2204 + 44 * k}"
    busy = y == 2026 and m >= 7
    mk_inv("S03", no, d, s03_lines(rng.randint(2, 3) if busy else rng.randint(1, 2),
                                   rng.randint(2, 3) if busy else rng.randint(1, 2),
                                   rng.randint(55, 75) if busy else rng.randint(30, 45), busy and m >= 8),
           f"Pacific Freight {no}.pdf", folder_of(d))
    # S04 rent (+ temporary storage licence Aug/Sep 2026)
    d = bday(D(y, m, 1))
    no = f"KBP/R/{y % 100}{m:02d}"
    mk_inv("S04", no, d, [("RENT", f"Monthly rent - Unit 9A, 9/F, Oceanic Godown Centre ({d:%b %Y})", 1, 80000.0)],
           f"KBP rent {d:%b%y}.pdf", folder_of(d))
    if y == 2026 and m in (8, 9):
        no = f"KBP/L/26{m:02d}"
        mk_inv("S04", no, bday(D(y, m, 3)), [("LIC", f"Licence fee - temporary storage Unit 3C, G/F, month-to-month ({d:%b %Y})", 1, 12000.0)],
               f"KBP storage {d:%b%y}.pdf", folder_of(d))
    # S05 SaaS
    no = f"CD-{10011 + 11 * k}"
    mk_inv("S05", no, d, [("CD-BIZ", f"CloudDesk Business - 25 seats, monthly subscription ({d:%b %Y})", 1, 1450.0)],
           f"invoice_{no}.pdf", folder_of(d))

HIST = [i for i in INVOICES if i["folder"]]  # Jul-Sep 2026, in the register
by_no = {i["no"]: i for i in INVOICES}
INV2291 = by_no["INV-2291"]
INV2291["entered"] = D(2026, 9, 3)

INBOX = [
    mk_inv("S01", "SP-2026-0917", D(2026, 9, 30),
           [("SP-4410", "电源管理模块", 2000, 118.00), ("SP-2208", "USB-C连接器组件", 3000, 23.50)],
           "scan_1002.pdf", "docs/invoices/inbox", bank=NEW_BANK[1], email=f"accounts@{FAKE_DOMAIN}"),
    mk_inv("S02", "DPE/INV/0388", D(2026, 9, 30), s02_lines(1500, 1000, 3000), "DPE-INV-0388.pdf", "docs/invoices/inbox"),
    mk_inv("S03", "INV-2291-R", D(2026, 9, 25), INV2291["lines"], "Invoice (3).pdf", "docs/invoices/inbox"),
    mk_inv("S03", "INV-2318", D(2026, 9, 30), s03_lines(2, 3, 60, True), "scan_0930_2.pdf", "docs/invoices/inbox"),
    mk_inv("S05", "CD-10044", D(2026, 10, 1), [("CD-BIZ", "CloudDesk Business - 25 seats, monthly subscription (Oct 2026)", 1, 1450.0)],
           "Invoice_CD-10044.pdf", "docs/invoices/inbox"),
]
for i in INBOX:
    INVOICES.remove(i)  # not entered anywhere yet
SCANNED = {"scan_1002.pdf", "scan_0930_2.pdf"}

# ----------------------------------------------------------------------------- customers & sales
SUFFIX = [("Ltd", "HK"), ("Ltd", "HK"), ("Pte. Ltd.", "SG"), ("Sdn. Bhd.", "MY"), ("Co., Ltd.", "TH"), ("Ltd", "HK"),
          ("Pte. Ltd.", "SG"), ("JSC", "VN"), ("Ltd", "HK")]
CUSTOMERS = [(f"{fake.last_name()} {rng.choice(['Electronics', 'Technology', 'Industrial', 'Components', 'Systems'])} {s}",
              c, rng.choice([30, 45])) for s, c in SUFFIX]
SALES = []
seq = 2511001
for y, m in months((2025, 11), (2026, 9)):
    target = 1_350_000 * rng.uniform(0.94, 1.12)
    w = [rng.uniform(0.5, 1.5) for _ in range(5)]
    for j, wt in enumerate(w):
        cust = rng.choice(CUSTOMERS)
        d = bday(D(y, m, 3 + j * 5))
        amt = round(target * wt / sum(w), -1)
        SALES.append(dict(no=f"HL-INV-{seq}", date=d, cust=cust[0], amount=float(amt),
                          recv=bday(d + timedelta(cust[2] + rng.randint(0, 12)))))
        seq += 1

# ----------------------------------------------------------------------------- general ledger
JOURNALS: list[dict] = []


def jnl(d, source, ref, contact, desc, lines, bank_desc=None):
    JOURNALS.append(dict(date=d, source=source, ref=ref, contact=contact, desc=desc, bank_desc=bank_desc,
                         lines=[(a, r2(dr), r2(cr)) for a, dr, cr in lines if dr or cr]))


PAYMENTS = []
Y0 = D(2026, 1, 1)
open_ap = 0.0
for inv in INVOICES:
    s = SUP[inv["sid"]]
    booked = r2(inv["total"] * fx(inv["currency"], inv["date"]))
    inv["amount_hkd"] = booked
    if inv["date"] >= Y0:
        jnl(inv["date"], "Payable Invoice", inv["no"], s["name_en"], f"{s['name_en']} {inv['no']}",
            [(inv["account"], booked, 0), ("800", 0, booked)])
    if inv["pay_date"] < Y0:
        continue
    if inv["date"] < Y0:
        open_ap += booked
    if inv["pay_date"] > CLOSE:
        continue
    paid = r2(inv["total"] * fx(inv["currency"], inv["pay_date"]))
    diff = r2(paid - booked)
    method = "TT OUT" if inv["currency"] != "HKD" else "FPS OUT"
    jnl(inv["pay_date"], "Payable Payment", inv["no"], s["name_en"], f"Payment {inv['no']}",
        [("800", booked, 0), ("497", max(diff, 0), max(-diff, 0)), ("090", 0, paid)],
        f"{method} {s['name_en'].upper().rstrip('.')} {inv['no']}")
    if inv["currency"] != "HKD":  # TT charge: own bank line, same journal
        JOURNALS[-1]["lines"] += [("404", 150.0, 0.0), ("090", 0.0, 150.0)]
        JOURNALS[-1]["bank_desc2"] = "TT CHARGE"
    PAYMENTS.append(dict(payment_date=inv["pay_date"], supplier_id=inv["sid"], supplier=s["name_en"],
                         invoice_no=inv["no"], amount=inv["total"], currency=inv["currency"], amount_hkd=paid,
                         bank_name=s["bank"].split(" (")[0], bank_account_paid=s["bank_acct"],
                         payment_ref=f"PAY-{inv['pay_date']:%y%m%d}-{inv['sid']}"))
open_ar = 0.0
for sl in SALES:
    if sl["date"] >= Y0:
        jnl(sl["date"], "Receivable Invoice", sl["no"], sl["cust"], f"Sales - {sl['cust']}",
            [("610", sl["amount"], 0), ("200", 0, sl["amount"])])
    elif sl["recv"] >= Y0:
        open_ar += sl["amount"]
    if Y0 <= sl["recv"] <= CLOSE:
        jnl(sl["recv"], "Receivable Payment", sl["no"], sl["cust"], f"Receipt {sl['no']}",
            [("090", sl["amount"], 0), ("610", 0, sl["amount"])], f"CR TRF {sl['cust'].upper()} {sl['no']}")

OPEN_CASH = 2_150_000.00
ob = [("090", OPEN_CASH, 0), ("610", open_ar, 0), ("630", 1_180_000, 0), ("710", 265_000, 0), ("711", 0, 96_000),
      ("800", 0, open_ap), ("970", 0, 1_000_000)]
plug = r2(sum(l[1] - l[2] for l in ob))
assert plug > 0
jnl(Y0, "Manual Journal", "OB-2026", "", "Opening balances b/f 31 Dec 2025", ob + [("960", 0, plug)])

# recurring spend money (vendor, account, amount fn, day, bank desc)
SPEND = [
    ("City Power Ltd", "445", lambda m: 4200 + (1650 if 6 <= m <= 9 else 0) + rng.randint(-250, 250), 12, "DD CITY POWER LTD"),
    ("Harbourtel Broadband", "489", lambda m: 1880, 5, "DD HARBOURTEL"),
    ("Oceanic Godown Centre Management Office", "471", lambda m: 6800 if m < 6 else 8000, 2, "AUTOPAY OCEANIC GODOWN MGMT"),
    (f"{fake.last_name()} Kee Hardware", "473", lambda m: rng.randint(10, 26) * 100, 18, "EPS HARDWARE"),
    ("Cross-border coach & hotel (staff claims)", "493", lambda m: rng.randint(15, 55) * 100, 20, "STAFF CLAIMS TRAVEL"),
    (f"{fake.last_name()} Stationery Co", "429", lambda m: rng.randint(12, 32) * 100, 22, "EPS STATIONERY"),
    ("OfficeSuite licences (card)", "485", lambda m: 1320, 3, "CARD OFFICESUITE"),
]
ONE_OFF = [
    (D(2026, 1, 12), "Peak Assurance Ltd", "433", 28800, "Annual business package policy 2026", "CHQ PEAK ASSURANCE"),
    (D(2026, 3, 20), "Lam & Partners CPA", "412", 45000, "2025 statutory audit fee", "FPS OUT LAM & PARTNERS CPA"),
    (D(2026, 7, 14), "Arctic Breeze Engineering Co", "473", 38500,
     "Emergency air-con compressor replacement - warehouse Unit 9A", "FPS OUT ARCTIC BREEZE ENG"),
    (D(2026, 9, 16), "Steelform Racking Ltd", "473", 9800, "Pallet racking repair after safety inspection",
     "FPS OUT STEELFORM RACKING"),
]
for y, m in months((2026, 1), (2026, 9)):
    for vendor, acct, fn, day, bd in SPEND:
        amt = float(fn(m))
        if not amt:
            continue
        desc = vendor + (" (revised fee from Jun 2026)" if acct == "471" and m >= 6 else "")
        jnl(bday(D(y, m, day)), "Spend Money", f"SM-{m:02d}-{acct}", vendor, desc, [(acct, amt, 0), ("090", 0, amt)], bd)
    pd = last_bday(y, m)
    jnl(pd, "Spend Money", f"PAY-{m:02d}", "Payroll", f"Payroll {pd:%b %Y} (18 staff)",
        [("477", 432000, 0), ("478", 26400, 0), ("090", 0, 405600), ("825", 0, 52800)], f"PAYROLL AUTOPAY {pd:%b%y}".upper())
    jnl(pd, "Spend Money", f"MPF-{m:02d}", "Orchid Trust MPF Scheme", "MPF contributions (ER + EE)",
        [("825", 52800, 0), ("090", 0, 52800)], "MPF ORCHID TRUST")
    interest = float(rng.randint(1100, 1900))
    jnl(pd, "Receive Money", f"INT-{m:02d}", CO["bank"], "Credit interest", [("090", interest, 0), ("270", 0, interest)],
        "CREDIT INTEREST")
    jnl(pd, "Spend Money", f"FEE-{m:02d}", CO["bank"], "Account maintenance fee", [("404", 120, 0), ("090", 0, 120)],
        "ACCOUNT MAINTENANCE FEE")
for d, vendor, acct, amt, desc, bd in ONE_OFF:
    jnl(d, "Spend Money", f"SM-{d:%m%d}", vendor, desc, [(acct, float(amt), 0), ("090", 0, float(amt))], bd)

JOURNALS.sort(key=lambda j: (j["date"], j["source"] != "Manual Journal", j["ref"]))
for n, j in enumerate(JOURNALS, 1):
    j["no"] = n
GL = [dict(date=j["date"], source=j["source"], no=j["no"], ref=j["ref"], contact=j["contact"], desc=j["desc"],
           code=a, dr=dr, cr=cr, bank_desc=j.get("bank_desc2") if (a, dr) == ("404", 150.0) or (a == "090" and cr == 150.0)
           else j["bank_desc"]) for j in JOURNALS for a, dr, cr in j["lines"]]


def balance(code, until):
    return r2(sum(r["dr"] - r["cr"] for r in GL if r["code"] == code and r["date"] <= until))


def actual(code, m):  # P&L sign: revenue positive as credit
    v = sum(r["dr"] - r["cr"] for r in GL if r["code"] == code and r["date"].month == m and r["date"].year == 2026)
    return r2(-v if ACC[code][3] == "Revenue" else v)


# ----------------------------------------------------------------------------- PDF engine
FONT_DIR = Path("/usr/share/fonts/noto-cjk")


def _idx(path):
    c = TTCollection(str(path), lazy=True)
    return next(i for i, f in enumerate(c.fonts) if f["name"].getDebugName(1).startswith("Noto") and
                f["name"].getDebugName(1).endswith(" CJK TC"))


FONTS = {("sans", ""): FONT_DIR / "NotoSansCJK-Regular.ttc", ("sans", "B"): FONT_DIR / "NotoSansCJK-Bold.ttc",
         ("serif", ""): FONT_DIR / "NotoSerifCJK-Regular.ttc", ("serif", "B"): FONT_DIR / "NotoSerifCJK-Bold.ttc"}
FONT_IDX = {k: _idx(p) for k, p in FONTS.items()}
PDF_DATE = datetime(2026, 10, 5, 9, 0, 0)


class Doc(FPDF):
    def __init__(self, footer=None, serif=False, when=PDF_DATE):
        super().__init__(format="A4")
        for (fam, st), p in FONTS.items():
            if fam == "sans" or serif:
                self.add_font(fam, st, str(p), collection_font_number=FONT_IDX[(fam, st)])
        self.footer_text = footer
        self.set_creation_date(when if isinstance(when, datetime) else datetime.combine(when, datetime.min.time()))
        self.set_margins(18, 15, 18)
        self.set_auto_page_break(True, 18)

    def footer(self):
        if self.footer_text:
            self.set_y(-13)
            self.set_font("sans", "", 7.5)
            self.set_text_color(110)
            self.cell(0, 5, self.footer_text.replace("{p}", str(self.page_no())), align="C")


def txt(p, s, size=10, style="", align="L", color=(0, 0, 0), fam="sans", h=None, w=0, gap=0):
    p.set_font(fam, style, size)
    p.set_text_color(*color)
    p.multi_cell(w, h or size * 0.48, s, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if gap:
        p.ln(gap)


def kv(p, x, y, items, wk, wv, size=9, h=5.2, bold_v=False):
    for i, (k, v) in enumerate(items):
        p.set_xy(x, y + i * h)
        p.set_font("sans", "", size)
        p.set_text_color(90)
        p.cell(wk, h, k)
        p.set_font("sans", "B" if bold_v else "", size)
        p.set_text_color(0)
        p.cell(wv, h, v)


def table(p, cols, rows, widths, aligns, size=8.5, fill=(232, 232, 232), h=6.2, border=1, text_color=(0, 0, 0)):
    p.set_font("sans", "B", size)
    p.set_fill_color(*fill)
    p.set_text_color(*text_color)
    for c, w in zip(cols, widths):
        p.cell(w, h, c, border=border, align="C", fill=True)
    p.ln(h)
    p.set_font("sans", "", size)
    p.set_text_color(0)
    for r in rows:
        for c, w, a in zip(r, widths, aligns):
            p.cell(w, h, str(c), border=border, align=a)
        p.ln(h)


def totals(p, items, x=112, wk=50, wv=30, h=6, size=9):
    for i, (k, v) in enumerate(items):
        last = i == len(items) - 1
        p.set_x(x)
        p.set_font("sans", "B" if last else "", size + (1 if last else 0))
        p.cell(wk, h, k, align="R")
        p.cell(wv, h, v, align="R", border="T" if last else 0)
        p.ln(h)


def stamp(p, x, y, top, bottom, color=(200, 30, 30), r=17):
    p.set_draw_color(*color)
    p.set_line_width(0.7)
    p.ellipse(x - r, y - r, 2 * r, 2 * r)
    p.set_text_color(*color)
    p.set_font("sans", "B", 7 if r >= 15 else 5.2)
    p.set_xy(x - r, y - 7)
    p.cell(2 * r, 4, top, align="C")
    p.set_font("sans", "B", 12)
    p.set_xy(x - r, y - 3)
    p.cell(2 * r, 6, "★", align="C")
    p.set_font("sans", "", 6.5)
    p.set_xy(x - r, y + 4)
    p.cell(2 * r, 4, bottom, align="C")
    p.set_draw_color(0)
    p.set_text_color(0)


def squiggle(p, x, y, seed, w=48):
    rr = random.Random(seed)
    pts = []
    for i in range(40):
        t = i / 39
        pts.append((x + t * w, y + 3.2 * __import__("math").sin(t * rr.uniform(9, 14)) * (1 - t * 0.5) + rr.uniform(-0.6, 0.6)))
    p.set_draw_color(20, 30, 110)
    p.set_line_width(0.45)
    p.polyline(pts)
    p.set_draw_color(0)
    p.set_line_width(0.2)


def rule(p, color=(0, 0, 0), wdt=0.4, gap=3):
    y = p.get_y() + 1
    p.set_draw_color(*color)
    p.set_line_width(wdt)
    p.line(p.l_margin, y, 210 - p.r_margin, y)
    p.set_line_width(0.2)
    p.set_draw_color(0)
    p.set_y(y + gap)


def out(p):
    return bytes(p.output())


# ----------------------------------------------------------------------------- invoice layouts
def inv_s01(inv):
    s, red = SUP["S01"], (170, 25, 25)
    p = Doc(when=inv["date"])
    p.add_page()
    txt(p, s["name_zh"], 20, "B", "C", red)
    txt(p, s["name_en"].upper(), 10, "", "C", red)
    txt(p, f"{s['addr_zh']}   电话 {s['tel']}   {s['reg'].replace('USCC', '统一社会信用代码')}", 7.5, "", "C", (90, 90, 90))
    rule(p, red, 0.7, 4)
    txt(p, "销 售 发 票", 16, "B", "C")
    txt(p, "COMMERCIAL INVOICE（出口）", 8, "", "C", (90, 90, 90), gap=4)
    y = p.get_y()
    kv(p, 18, y, [("购货单位：", CO["name_zh"]), ("", CO["name_en"]), ("地址：", CO["addr_zh"][:12]), ("", CO["addr_zh"][12:])], 18, 90)
    kv(p, 128, y, [("发票号码：", inv["no"]), ("开票日期：", zh_date(inv["date"])), ("付款期限：", zh_date(inv["due"])),
                   ("合同编号：", s["contract_no"])], 18, 46, bold_v=True)
    p.set_y(y + 26)
    rows = [(i + 1, c, d, f"{q:,}", money(u), money(q * u)) for i, (c, d, q, u) in enumerate(inv["lines"])]
    table(p, ["序号", "货号", "品名及规格", "数量", "单价（元）", "金额（元）"], rows, [12, 24, 60, 22, 28, 28], "CCLRRR",
          fill=(250, 228, 228))
    p.ln(2)
    totals(p, [("小计（RMB）", money(inv["subtotal"])), ("税率 0%（出口免税）", "0.00"), ("价税合计 人民币（RMB）", money(inv["total"]))])
    p.ln(6)
    txt(p, "收款账户信息", 9.5, "B", color=red)
    y = p.get_y() + 1
    kv(p, 18, y, [("收款银行：", inv["bank_name"].split(" (")[1].rstrip(")")), ("账户名称：", s["name_zh"]),
                  ("银行账号：", inv["bank"])], 20, 100, bold_v=True)
    p.set_y(y + 20)
    txt(p, f"付款条件：发票日起{s['terms']}天内电汇。如有疑问，请联系 {inv['email']}", 8, color=(90, 90, 90), gap=8)
    y = p.get_y()
    kv(p, 18, y, [("开票人：", "张丽"), ("复核：", "陈国华")], 14, 30)
    stamp(p, 160, y + 6, "深圳市零件有限公司", "财务专用章")
    return out(p)


def inv_s02(inv):
    s, blue = SUP["S02"], (20, 60, 120)
    p = Doc(when=inv["date"])
    p.add_page()
    p.set_fill_color(*blue)
    p.rect(0, 0, 210, 30, "F")
    p.set_xy(18, 7)
    p.set_text_color(255)
    p.set_font("sans", "B", 12)
    p.cell(110, 7, s["name_en"].upper())
    p.set_xy(18, 15)
    p.set_font("sans", "", 11)
    p.cell(120, 6, s["name_zh"])
    p.set_xy(140, 8)
    p.set_font("sans", "B", 13)
    p.cell(52, 8, "COMMERCIAL INVOICE", align="R")
    p.set_xy(140, 16)
    p.set_font("sans", "", 10)
    p.cell(52, 6, "商业发票", align="R")
    p.set_y(34)
    txt(p, f"{s['addr_en']}  |  {s['addr_zh']}  |  Tel {s['tel']}  |  {s['reg']}", 7.5, color=(80, 80, 80), gap=5)
    y = p.get_y()
    kv(p, 18, y, [("Bill to 买方:", CO["name_en"]), ("", CO["name_zh"]), *[("", x) for x in split2(CO["addr_en"], 44)]], 26, 80)
    kv(p, 122, y, [("Invoice No. 发票号:", inv["no"]), ("Date 日期:", inv["date"].isoformat()),
                   ("Due 到期日:", inv["due"].isoformat()), ("Terms 付款条件:", "Net 30 days"),
                   ("Contract 合同:", s["contract_no"])], 34, 36, bold_v=True)
    p.set_y(y + 34)
    rows = [(c, d, f"{q:,}", money(u), money(q * u)) for c, d, q, u in inv["lines"]]
    table(p, ["Item 货号", "Description 描述", "Qty 数量", "Unit USD 单价", "Amount USD 金额"], rows,
          [24, 70, 22, 28, 30], "LLRRR", fill=(215, 225, 240))
    p.ln(2)
    totals(p, [("Subtotal 小计", money(inv["subtotal"])), ("VAT 0% (export) 增值税", "0.00"),
               ("TOTAL USD 合计", money(inv["total"]))])
    p.ln(6)
    txt(p, "Remittance / 汇款信息", 9.5, "B", color=blue)
    txt(p, f"Beneficiary: {s['name_en']}\nBank: {s['bank']}\nAccount No.: {inv['bank']}", 8.5, h=4.6, gap=4)
    txt(p, "Goods shipped FCA Dongguan per contract. 货物按合同FCA东莞交付。", 8, color=(80, 80, 80))
    return out(p)


def inv_s03(inv):
    s, green = SUP["S03"], (16, 110, 70)
    p = Doc(when=inv["date"])
    p.add_page()
    p.set_fill_color(*green)
    p.rect(18, 14, 22, 22, "F")
    p.set_xy(18, 20)
    p.set_text_color(255)
    p.set_font("sans", "B", 13)
    p.cell(22, 10, "PFL", align="C")
    p.set_xy(90, 14)
    p.set_text_color(*green)
    p.set_font("sans", "B", 14)
    p.cell(102, 7, s["name_en"].upper(), align="R")
    p.set_text_color(80)
    p.set_font("sans", "", 8)
    for i, line in enumerate([s["addr_en"], f"Tel {s['tel']}  |  {s['email']}", s["reg"]]):
        p.set_xy(60, 22 + i * 4.5)
        p.cell(132, 4.5, line, align="R")
    p.set_y(44)
    txt(p, "INVOICE", 22, "B", color=green, gap=3)
    y = p.get_y()
    kv(p, 18, y, [("Bill to", CO["name_en"]), *[("", x) for x in split2(CO["warehouse"], 50)]], 16, 90)
    kv(p, 130, y, [("Invoice no.", inv["no"]), ("Date", en_date(inv["date"])), ("Due date", en_date(inv["due"])),
                   ("Account", "HLT-0042")], 22, 40, bold_v=True)
    p.set_y(y + 25)
    rows = [(c, d, q, f"{FREIGHT[c][1]}", money(u), money(q * u)) for c, d, q, u in inv["lines"]]
    table(p, ["Code", "Description", "Qty", "Unit", "Rate HKD", "Amount HKD"], rows, [16, 80, 12, 20, 22, 24],
          "LLRCRR", fill=(210, 235, 222), border="B")
    p.ln(2)
    totals(p, [("Subtotal", money(inv["subtotal"])), ("TOTAL HKD", money(inv["total"]))])
    p.ln(8)
    txt(p, f"Payment within {s['terms']} days to {s['bank']}, account {inv['bank']} ({s['name_en']}).", 8.5)
    txt(p, "Rates per Pacific Freight 2026 rate card. E. & O. E.", 8, color=(100, 100, 100))
    return out(p)


def inv_s04(inv):
    s = SUP["S04"]
    p = Doc(when=inv["date"])
    p.add_page()
    txt(p, s["name_en"].upper(), 15, "B", "C", (60, 60, 60))
    txt(p, s["name_zh"], 11, "", "C", (60, 60, 60))
    txt(p, f"{s['addr_en']}  ·  Tel {s['tel']}  ·  {s['reg']}", 7.5, "", "C", (110, 110, 110))
    rule(p, (120, 120, 120), 0.3, 6)
    txt(p, "DEBIT NOTE", 14, "B", "C", gap=4)
    y = p.get_y()
    kv(p, 18, y, [("To:", CO["name_en"]), *[("", x) for x in split2(CO["addr_en"], 56)]], 12, 100)
    kv(p, 130, y, [("Debit note:", inv["no"]), ("Date:", en_date(inv["date"])), ("Due:", en_date(inv["due"])),
                   ("Lease ref:", "KBP/L/2024/09A")], 22, 40, bold_v=True)
    p.set_y(y + 26)
    rows = [(d, money(u * q)) for _, d, q, u in inv["lines"]]
    table(p, ["Particulars", "Amount (HK$)"], rows, [140, 34], "LR", border=1, fill=(238, 238, 238))
    p.ln(2)
    totals(p, [("Total due HK$", money(inv["total"]))])
    p.ln(8)
    txt(p, f"Please pay by autopay or transfer to {s['bank']} a/c {inv['bank']}. Rent is payable in advance.", 8.5)
    txt(p, "This is a computer-generated debit note. No signature is required.", 7.5, color=(120, 120, 120))
    return out(p)


def inv_s05(inv):
    s, purple = SUP["S05"], (92, 50, 180)
    p = Doc(when=inv["date"])
    p.add_page()
    p.set_text_color(*purple)
    p.set_font("sans", "B", 20)
    p.cell(100, 10, "CloudDesk")
    p.set_font("sans", "", 20)
    p.set_text_color(150)
    p.cell(74, 10, "Invoice", align="R")
    p.ln(14)
    txt(p, f"{s['name_en']} · {s['addr_en']} · {s['reg']}", 7.5, color=(120, 120, 120), gap=5)
    y = p.get_y()
    kv(p, 18, y, [("Billed to", CO["name_en"]), ("", "Attn: Anna Chan"), ("", PEOPLE["anna"][1])], 20, 80)
    kv(p, 128, y, [("Invoice #", inv["no"]), ("Issued", inv["date"].strftime("%B %d, %Y")),
                   ("Due", inv["due"].strftime("%B %d, %Y")), ("Order form", "OF-2025-3381")], 24, 40, bold_v=True)
    p.set_y(y + 26)
    rows = [(d, q, money(u), money(q * u)) for _, d, q, u in inv["lines"]]
    table(p, ["Description", "Qty", "Unit price", "Amount (USD)"], rows, [104, 14, 26, 30], "LRRR", border="B",
          fill=(236, 230, 250))
    p.ln(2)
    totals(p, [("Subtotal", money(inv["subtotal"])), ("Tax", "0.00"), ("Amount due (USD)", money(inv["total"]))])
    p.ln(8)
    txt(p, f"Pay by wire: {s['bank']}, account {inv['bank']}. Questions: {s['email']}", 8.5)
    return out(p)


RENDER = {"S01": inv_s01, "S02": inv_s02, "S03": inv_s03, "S04": inv_s04, "S05": inv_s05}


def scan(pdf_bytes, seed):
    """Render to image, grayscale, rotate, add paper tone/noise/blur, embed as image-only PDF."""
    rr = random.Random(seed)
    page = fitz.open(stream=pdf_bytes, filetype="pdf")[0]
    pix = page.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    img = img.point(lambda v: int(v * 0.86 + 22))  # paper tone, lifted blacks
    img = img.rotate(rr.choice([-1, 1]) * rr.uniform(0.5, 1.5), resample=Image.BICUBIC, fillcolor=236)
    noise = Image.frombytes("L", img.size, rr.randbytes(img.size[0] * img.size[1]))
    img = Image.blend(img, noise, 0.07).filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=62)
    p = FPDF(format="A4")
    p.set_creation_date(PDF_DATE)
    p.set_producer("DocuScan 3.2")
    p.add_page()
    p.image(io.BytesIO(buf.getvalue()), x=0, y=0, w=210, h=297)
    return out(p)


# ----------------------------------------------------------------------------- contracts
BOILER_SUPPLY = [
    ("Goods shall conform to the agreed specifications and pass the Buyer's incoming inspection.", "货物须符合约定规格并通过买方来料检验。"),
    ("Delivery FCA {city}; risk passes on handover to the Buyer's nominated carrier.", "交货条件：FCA {city_zh}；货物交付买方指定承运人时风险转移。"),
    ("Defective goods reported within 90 days shall be replaced or credited free of charge.", "90日内报告的不良品应免费更换或退款。"),
    ("Neither party is liable for delay caused by force majeure.", "因不可抗力导致的延误，双方均不承担责任。"),
    ("Each party shall keep the terms of this Agreement confidential.", "双方应对本协议条款保密。"),
    ("Amendments are valid only in writing signed by both parties' authorised signatories.", "本协议的任何修改须经双方授权代表书面签署方为有效。"),
    ("This Agreement is governed by Hong Kong law; disputes go to arbitration in Hong Kong.", "本协议适用香港法律，争议提交香港仲裁解决。"),
    ("In case of conflict, the English version prevails.", "中英文版本如有冲突，以英文版本为准。"),
]
BOILER_LEASE = [
    "The Tenant shall keep the interior of the Premises in good and tenantable repair.",
    "The Tenant shall not assign, sublet or part with possession of the Premises.",
    "The Tenant shall comply with the Deed of Mutual Covenant and the building rules.",
    "The Landlord shall keep the main structure, roof and exterior walls in proper repair.",
    "The Tenant shall insure its stock and maintain public liability cover of at least HK$10,000,000.",
    "No alterations shall be made to the Premises without the Landlord's prior written consent.",
    "Notices may be served at the addresses stated above by hand or by registered post.",
    "Time shall be of the essence in respect of all payments under this Agreement.",
]


def clause(p, num, title, body, fam="sans", size=9.5, align=None):
    align = align or ("J" if fam == "serif" else "L")
    txt(p, f"{num}  {title}", size + 0.5, "B", fam=fam, gap=1)
    for sub, t in body:
        p.set_x(p.l_margin)
        p.set_font(fam, "", size)
        p.cell(10, size * 0.5, sub)
        p.multi_cell(0, size * 0.5, t, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        p.ln(1)
    p.ln(2)


def supply_agreement(sid):
    s, city = SUP[sid], ("Shenzhen", "深圳") if sid == "S01" else ("Dongguan", "东莞")
    cur, sym = ("RMB", "人民币") if sid == "S01" else ("USD", "美元")
    p = Doc(footer=f"{s['contract_no']}  ·  Page {{p}} / {{nb}}  ·  第{{p}}页", when=D(2025, 12, 12))
    p.add_page()
    txt(p, "SUPPLY AGREEMENT  供货协议", 16, "B", "C")
    txt(p, f"Agreement No. 协议编号: {s['contract_no']}   ·   Effective 生效日期: 1 January 2026", 9, "", "C", gap=5)
    txt(p, f"Buyer 买方: {CO['name_en']} {CO['name_zh']}, BR No. {CO['br']}, {CO['addr_en']}", 9, gap=1)
    txt(p, f"Seller 卖方: {s['name_en']} {s['name_zh']}, {s['reg']}, {s['addr_en']}", 9, gap=4)
    clause(p, "1", "Scope 供货范围", [("1.1", f"The Seller supplies the electronic components listed in clause 4.2 to the Buyer on purchase order. 卖方按买方订单供应第4.2条所列电子元器件。")])
    clause(p, "2", "Term 期限", [("2.1", "1 January 2026 to 31 December 2026, renewable by written agreement. 2026年1月1日至2026年12月31日，经书面同意可续期。")])
    clause(p, "3", "Orders 订单", [("3.1", "Each purchase order states item code, quantity and delivery date. 每份订单须列明货号、数量及交货日期。")])
    p.set_font("sans", "B", 10)
    clause(p, "4", "Prices 价格", [
        ("4.1", f"Prices are fixed in {cur} for the Term, FCA {city[0]}, export VAT 0%. 价格于协议期内以{sym}固定，FCA{city[1]}，出口增值税0%。"),
        ("4.2", "Price schedule 价格表:")])
    rows = [(c, f"{en} / {zh}", u, f"{cur} {pr:,.2f}") for c, (en, zh, u, pr) in PRICES[sid].items()]
    table(p, ["Item code 货号", "Description 品名", "Unit 单位", "Unit price 单价"], rows, [28, 96, 20, 30], "LLCR", size=8.5)
    p.ln(2)
    txt(p, "4.3  Any price change requires a written amendment signed by both parties before invoicing. 任何价格调整须在开票前经双方书面签署修订。", 9.5, gap=3)
    clause(p, "5", "Payment 付款", [
        ("5.1", f"Payment within {s['terms']} days of invoice date by telegraphic transfer. 发票日起{s['terms']}天内电汇付款。"),
        ("5.2", f"Seller's designated account 卖方指定账户: {s['bank']}, account name {s['name_en']}, account no. {s['bank_acct']}."),
        ("5.3", "Any change of bank account must be confirmed in writing by both parties' authorised signatories; email notice alone is not valid. 银行账户变更须经双方授权代表书面确认，仅凭电子邮件通知无效。")])
    clause(p, "6", "General 一般条款", [(f"6.{i}", en.format(city=city[0]) + "\n" + zh.format(city_zh=city[1]))
                                        for i, (en, zh) in enumerate(BOILER_SUPPLY, 1)])
    p.ln(4)
    y = p.get_y()
    if y > 240:
        p.add_page()
        y = p.get_y()
    for x, who, name in [(18, "For the Buyer 买方", "David Wong, Director"), (112, "For the Seller 卖方",
                                                                            "Zhang Wei, General Manager" if sid == "S01" else "Li Ming, Sales Director")]:
        kv(p, x, y, [(who, ""), ("", ""), ("", ""), ("Name:", name), ("Date:", "12 Dec 2025")], 14, 60)
        squiggle(p, x + 4, y + 11, len(name) * 7 + x)
    stamp(p, 178, y - 2, s["name_zh"], "合同专用章", r=14)
    return out(p)


def rate_card():
    s, green = SUP["S03"], (16, 110, 70)
    p = Doc(when=D(2025, 12, 1))
    p.add_page()
    txt(p, s["name_en"].upper(), 15, "B", color=green)
    txt(p, f"{s['addr_en']} · {s['reg']}", 8, color=(90, 90, 90), gap=4)
    txt(p, "CUSTOMER RATE CARD 2026", 14, "B", gap=1)
    txt(p, f"Customer: {CO['name_en']} (account HLT-0042)   ·   Valid 1 Jan - 31 Dec 2026", 9, gap=4)
    table(p, ["Code", "Service", "Unit", "Rate (HKD)"], [(c, d, u, money(r)) for c, (d, u, r) in FREIGHT.items()],
          [20, 102, 26, 26], "LLCR", fill=(210, 235, 222))
    p.ln(4)
    for n in ["Rates exclude government fees, tunnel tolls and storage beyond 3 free days.",
              "Peak season surcharge applies to all containers moved 1 Aug - 31 Oct.",
              f"Invoices are issued per month of service; payment terms {s['terms']} days."]:
        txt(p, "•  " + n, 9, gap=1)
    p.ln(6)
    txt(p, "Accepted for the customer: Anna Chan, Finance Manager, 3 Dec 2025", 9)
    squiggle(p, 30, p.get_y() + 6, 77)
    return out(p)


LEASE_NEW = dict(ref="KBP/L/2027/09A", signed=D(2026, 9, 29), start=D(2027, 1, 1), end=D(2029, 12, 31), rent=82400.0,
                 esc=0.03, deposit=247200)
LEASE_OLD = dict(ref="KBP/L/2024/09A", signed=D(2023, 11, 20), start=D(2024, 1, 1), end=D(2026, 12, 31), rent=80000.0,
                 esc=0.0, deposit=240000)


def rent_schedule(L):
    return [(L["start"].year + i, r2(L["rent"] * (1 + L["esc"]) ** i)) for i in range(L["end"].year - L["start"].year + 1)]


def lease(L):
    s = SUP["S04"]
    new = L["esc"] > 0
    p = Doc(footer=f"Tenancy Agreement {L['ref']}  ·  Page {{p}} of {{nb}}", serif=True, when=L["signed"])
    p.add_page()
    txt(p, "TENANCY AGREEMENT", 17, "B", "C", fam="serif")
    txt(p, "租 約", 12, "", "C", fam="serif")
    txt(p, f"Ref: {L['ref']}", 9, "", "C", (90, 90, 90), gap=6)
    txt(p, f"THIS AGREEMENT is made on {en_date(L['signed'])}", 10.5, fam="serif", gap=3)
    txt(p, "BETWEEN", 10.5, "B", fam="serif", gap=2)
    txt(p, f"(1)  {s['name_en'].upper()} ({s['name_zh']}), {s['reg']}, whose registered office is at {s['addr_en']} (the \"Landlord\"); and", 10.5, fam="serif", gap=2)
    txt(p, f"(2)  {CO['name_en'].upper()} ({CO['name_zh']}), BR No. {CO['br']}, whose registered office is at {CO['addr_en']} (the \"Tenant\").", 10.5, fam="serif", gap=5)
    txt(p, "IT IS AGREED as follows:", 10.5, fam="serif", gap=4)
    clause(p, "1.", "PREMISES", [("1.1", f"The Landlord lets and the Tenant takes {CO['warehouse']} with a gross floor area of approximately 6,200 sq. ft. (the \"Premises\")."),
                                 ("1.2", "The Premises shall be used as a warehouse with ancillary office only.")], "serif", 10.5)
    if new:
        p.add_page()
    clause(p, "2.", "TERM", [("2.1", f"The term is {L['end'].year - L['start'].year + 1} years from {en_date(L['start'])} to {en_date(L['end'])}, both days inclusive (the \"Term\").")], "serif", 10.5)
    clause(p, "3.", "DEPOSIT AND TENANT'S OBLIGATIONS",
           [("3.1", f"The Tenant shall pay a security deposit of HK${L['deposit']:,} on signing, refundable without interest on expiry.")] +
           [(f"3.{i}", t) for i, t in enumerate(BOILER_LEASE if new else BOILER_LEASE[:4], 2)], "serif", 10.5)
    p.add_page()
    if new:
        body = [("4.1", f"The monthly rent shall be HK${L['rent']:,.0f} (Hong Kong Dollars Eighty-Two Thousand Four Hundred) "
                        f"exclusive of rates and management fees, payable from {en_date(L['start'])}."),
                ("4.2", "On each 1 January during the Term the monthly rent shall increase by three per cent (3%) over the monthly rent payable in the preceding year."),
                ("4.3", "For the avoidance of doubt, the monthly rent for each year of the Term is:")]
    else:
        body = [("4.1", f"The monthly rent shall be HK${L['rent']:,.0f} (Hong Kong Dollars Eighty Thousand) exclusive of rates and management fees, fixed for the whole Term."),
                ("4.2", "No rent review shall take place during the Term.")]
    clause(p, "4.", "RENT" + (" AND RENT REVIEW" if new else ""), body, "serif", 10.5)
    if new:
        table(p, ["Period", "Monthly rent (HK$)"], [(f"1 Jan {y} - 31 Dec {y}", money(r)) for y, r in rent_schedule(L)],
              [70, 45], "LR", size=9.5)
        p.ln(3)
    clause(p, "5.", "PAYMENT, RATES AND MANAGEMENT FEES",
           [("5.1", f"Rent is payable monthly in advance on the first day of each month by autopay to the Landlord's account with {s['bank']}, a/c {s['bank_acct']}."),
            ("5.2", "Rates and management fees are payable by the Tenant separately to the Government and the building manager.")], "serif", 10.5)
    clause(p, "6.", "GOVERNING LAW", [("6.1", "This Agreement is governed by the laws of the Hong Kong Special Administrative Region.")], "serif", 10.5)
    p.ln(4)
    txt(p, "IN WITNESS whereof the parties have signed this Agreement on the date first written above.", 10, fam="serif", gap=8)
    y = p.get_y()
    for x, who, name in [(18, "SIGNED by the Landlord", "Raymond Ho, Director"), (112, "SIGNED by the Tenant", "David Wong, Director")]:
        p.set_xy(x, y)
        p.set_font("serif", "B", 9.5)
        p.cell(80, 5, who)
        p.set_xy(x, y + 22)
        p.set_draw_color(0)
        p.line(x, y + 21, x + 70, y + 21)
        p.set_font("serif", "", 9)
        p.cell(80, 5, f"{name}, for and on behalf of")
        p.set_xy(x, y + 27)
        p.cell(80, 5, s["name_en"] if x == 18 else CO["name_en"])
        squiggle(p, x + 6, y + 15, x * 3 + L["signed"].year)
    stamp(p, 98, y + 9, s["name_zh"], "LANDLORD", (40, 60, 160), 12)
    stamp(p, 188, y + 9, CO["name_zh"], "TENANT", (190, 30, 30), 12)
    p.set_y(y + 40)
    txt(p, "Witness: Anna Chan, Finance Manager, Harbour Lane Trading Ltd", 9, fam="serif")
    return out(p)


def order_form():
    s, purple = SUP["S05"], (92, 50, 180)
    p = Doc(when=D(2025, 11, 10))
    p.add_page()
    txt(p, "CloudDesk", 20, "B", color=purple)
    txt(p, "ORDER FORM  OF-2025-3381", 12, "B", gap=1)
    txt(p, f"{s['name_en']}, {s['addr_en']}", 8, color=(110, 110, 110), gap=5)
    y = p.get_y()
    kv(p, 18, y, [("Customer", f"{CO['name_en']}, {CO['addr_en'][:60]}"), ("Billing contact", PEOPLE["anna"][1]),
                          ("Subscription start", "November 16, 2025"), ("Initial term", "12 months (Nov 16, 2025 - Nov 15, 2026)"),
                          ("Renewal date", "November 16, 2026"), ("Billing", "Monthly in advance, net 15, USD")], 34, 130)
    p.set_y(y + 36)
    table(p, ["Product", "Seats", "Price / seat / month", "Monthly fee"], [("CloudDesk Business (helpdesk + shared inbox)", 25, "USD 58.00", "USD 1,450.00")],
          [84, 16, 40, 34], "LRRR", fill=(236, 230, 250))
    p.ln(5)
    terms = [("1. Auto-renewal.", "This Order Form renews automatically on the Renewal Date for successive 12-month terms at the then-current list price "
                                  "unless either party gives written notice of non-renewal at least 30 days before the Renewal Date."),
             ("2. Notice.", "Non-renewal notices must be sent to legal@clouddesk.io. Notices sent via in-app chat are not valid."),
             ("3. Fees.", "Fees are non-refundable. Seats may be added at any time and are co-terminous with this Order Form."),
             ("4. Terms.", "This Order Form is governed by the CloudDesk Master Subscription Agreement (v4.1).")]
    for h, t in terms:
        txt(p, h, 9.5, "B")
        txt(p, t, 9, gap=2)
    p.ln(6)
    txt(p, "Signed for the Customer: Anna Chan, Finance Manager — November 10, 2025", 9)
    squiggle(p, 30, p.get_y() + 6, 31)
    return out(p)


def bank_statement(lines, opening):
    navy = (16, 40, 90)
    p = Doc(footer="Victoria Harbour Bank Limited (fictional) · Statement 2026-09 · Page {p} of {nb}", when=D(2026, 10, 2))
    p.add_page()
    p.set_fill_color(*navy)
    p.rect(0, 0, 210, 24, "F")
    p.set_xy(18, 7)
    p.set_text_color(255)
    p.set_font("sans", "B", 15)
    p.cell(120, 8, "VICTORIA HARBOUR BANK")
    p.set_font("sans", "", 9)
    p.set_xy(120, 8)
    p.cell(72, 6, "維港銀行  ·  Business Integrated Account", align="R")
    p.set_y(30)
    kv(p, 18, 30, [("Account name", CO["name_en"]), ("Account no.", CO["bank_acct"] + " (HKD Current)"),
                   ("Statement period", "01 Sep 2026 - 30 Sep 2026"), ("Branch", "Kwun Tong Business Centre")], 30, 100)
    p.set_y(54)
    rows, bal = [], opening
    rows.append(("01 Sep", "BALANCE BROUGHT FORWARD", "", "", money(opening)))
    for d, desc, amt in lines:
        bal = r2(bal + amt)
        rows.append((d.strftime("%d %b"), desc[:62], money(-amt) if amt < 0 else "", money(amt) if amt > 0 else "", money(bal)))
    rows.append(("30 Sep", "CLOSING BALANCE", "", "", money(bal)))
    table(p, ["Date", "Transaction details", "Withdrawal", "Deposit", "Balance"], rows, [16, 88, 24, 24, 26],
          "LLRRR", size=7.5, h=5.2, border="B", fill=(220, 226, 240))
    p.ln(4)
    dep, wd = sum(a for _, _, a in lines if a > 0), -sum(a for _, _, a in lines if a < 0)
    totals(p, [("Opening balance", money(opening)), ("Total deposits", money(dep)), ("Total withdrawals", money(wd)),
               ("Closing balance HKD", money(bal))], size=8.5)
    return out(p), bal


# ----------------------------------------------------------------------------- sheets
HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")
NUM = "#,##0.00"


def header(ws, cols, widths, row=1):
    for i, (c, w) in enumerate(zip(cols, widths), 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill, cell.font, cell.alignment = HDR_FILL, HDR_FONT, Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = w
    ws.freeze_panes = f"A{row + 1}"


def save_wb(wb, rel, when):
    wb.properties.creator = "Anna Chan"
    wb.properties.lastModifiedBy = "Ken Lau"
    stamp_ = when.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    buf = io.BytesIO()
    wb.save(buf)
    zin, ob_ = zipfile.ZipFile(buf), io.BytesIO()
    with zipfile.ZipFile(ob_, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            b = zin.read(it.filename)
            if it.filename == "docProps/core.xml":
                b = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*", rb"\g<1>" + stamp_, b)
            zi = zipfile.ZipInfo(it.filename, date_time=when.timetuple()[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, b)
    write(rel, ob_.getvalue())


def reg_rows(until, as_of):
    rows = []
    for inv in sorted([i for i in HIST if i["date"] <= until], key=lambda i: (i["date"], i["sid"], i["no"])):
        s = SUP[inv["sid"]]
        status = "Paid" if inv["pay_date"] <= as_of else "Approved"
        rows.append([inv["date"], inv["sid"], s["name_en"], inv["no"], inv["currency"], inv["total"],
                     fx(inv["currency"], inv["date"]), inv["amount_hkd"], inv["account"], inv["due"], status,
                     f"{inv['folder']}/{inv['file']}"])
    return rows


REG_COLS = ["date", "supplier_id", "supplier", "invoice_no", "currency", "amount", "fx_rate", "amount_hkd",
            "account_code", "due_date", "status", "source_file"]


def write_register(until, as_of, when):
    wb = Workbook()
    ws = wb.active
    ws.title = "Register"
    header(ws, REG_COLS, [11, 10, 34, 16, 9, 14, 8, 14, 12, 11, 10, 52])
    for r, row in enumerate(reg_rows(until, as_of), 2):
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=v)
        ws.cell(row=r, column=8, value=f"=ROUND(F{r}*G{r},2)")
        for c in (1, 10):
            ws.cell(row=r, column=c).number_format = "yyyy-mm-dd"
        for c in (6, 8):
            ws.cell(row=r, column=c).number_format = NUM
        ws.cell(row=r, column=7).number_format = "0.0000"
    ws.auto_filter.ref = f"A1:L{ws.max_row}"
    save_wb(wb, "sheets/invoice_register.xlsx", when)


def write_master(when):
    wb = Workbook()
    ws = wb.active
    ws.title = "Suppliers"
    cols = ["id", "name_en", "name_zh", "email_domain", "bank_name", "bank_account", "currency", "payment_terms", "contract_file"]
    header(ws, cols, [6, 38, 20, 20, 60, 22, 9, 14, 44])
    for sid, s in SUP.items():
        ws.append([sid, s["name_en"], s["name_zh"], s["domain"], s["bank"], s["bank_acct"], s["currency"],
                   f"{s['terms']} days", s["contract"]])
    save_wb(wb, "sheets/supplier_master.xlsx", when)


def write_fx(until_month, when):
    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly"
    header(ws, ["month", "USD_HKD", "RMB_HKD", "source"], [10, 10, 10, 40])
    for k, (u, r) in FX.items():
        if k <= until_month:
            ws.append([k, u, r, "Month-start rate, Victoria Harbour Bank board rate"])
    save_wb(wb, "sheets/fx_rates.xlsx", when)


def write_bva(until_m, when):
    wb = Workbook()
    ws = wb.active
    ws.title = "YTD"
    ws["A1"] = f"Harbour Lane Trading Ltd - Budget vs Actual 2026, YTD {'Jan-' + D(2026, until_m, 1).strftime('%b') if until_m else '(no actuals yet)'}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = "Budget approved by D. Wong 20 Jan 2026. Actuals from GL export. Variance = Actual - Budget (expenses: positive = over budget)."
    header(ws, ["code", "account", "group", "budget_ytd", "actual_ytd", "variance", "variance_pct"], [7, 34, 20, 14, 14, 14, 12], row=4)
    r = 5
    for code in PL_CODES:
        b = sum(budget(code, m) for m in range(1, until_m + 1)) if until_m else sum(budget(code, m) for m in range(1, 13))
        a = sum(actual(code, m) for m in range(1, until_m + 1))
        ws.append([code, ACC[code][1], ACC[code][3], b, r2(a), f"=E{r}-D{r}", f'=IF(D{r}=0,"",F{r}/D{r})'])
        r += 1
    last = r - 1
    ws.append([])
    r += 1
    ws.cell(row=r, column=2, value="By group").font = Font(bold=True)
    for g in ["Revenue", "Cost of sales", "Freight & logistics", "Facilities", "Staff", "Admin"]:
        r += 1
        ws.append(["", g, "group total", f'=SUMIF($C$5:$C${last},B{r},D$5:D${last})', f'=SUMIF($C$5:$C${last},B{r},E$5:E${last})',
                   f"=E{r}-D{r}", f'=IF(D{r}=0,"",F{r}/D{r})'])
    for row in ws.iter_rows(min_row=5, min_col=4, max_col=7):
        for c in row:
            c.number_format = "0.0%" if c.column == 7 else "#,##0"
    if not until_m:
        ws.cell(row=4, column=4, value="budget_fy")
    m_ws = wb.create_sheet("Budget monthly")
    header(m_ws, ["code", "account"] + [D(2026, m, 1).strftime("%b") for m in range(1, 13)], [7, 34] + [11] * 12)
    for code in PL_CODES:
        m_ws.append([code, ACC[code][1]] + [budget(code, m) for m in range(1, 13)])
    a_ws = wb.create_sheet("Actual monthly")
    header(a_ws, ["code", "account"] + [D(2026, m, 1).strftime("%b") for m in range(1, until_m + 1)], [7, 34] + [12] * 9)
    for code in PL_CODES:
        a_ws.append([code, ACC[code][1]] + [actual(code, m) for m in range(1, until_m + 1)])
    save_wb(wb, "sheets/budget_vs_actual_2026.xlsx", when)


FC_ROWS = [  # label, account(s), 2027 monthly, 2028 growth
    ("Revenue", "200", 1_420_000, 0.04), ("Cost of goods sold", "310", 625_000, 0.04), ("Gross profit", "", None, None),
    ("Salaries & MPF", "477/478", 470_000, 0.04), ("Rent", "469", 80_000, 0.0), ("Freight", "425", 24_000, 0.03),
    ("Software", "485", 12_700, 0.0), ("Utilities & building mgmt", "445/471", 13_500, 0.03),
    ("Other opex", "4xx", 40_000, 0.03), ("Total opex", "", None, None), ("EBITDA", "", None, None),
]
RENT_ROW = 9


def write_forecast(when):
    wb = Workbook()
    ws = wb.active
    ws.title = "Forecast"
    ws["A1"] = "Harbour Lane Trading Ltd - P&L forecast 2027-2028 (HKD)"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = "v1, 14 Aug 2026, prepared by A. Chan. Rent flat pending lease renewal (D. Wong)."
    mons = [D(2027 + i // 12, i % 12 + 1, 1) for i in range(24)]
    header(ws, ["line", "acct"] + [m.strftime("%b-%y") for m in mons], [26, 9] + [11] * 24, row=4)
    from openpyxl.utils import get_column_letter as L
    for i, (label, acct, base, g) in enumerate(FC_ROWS):
        r = 5 + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=acct)
        for j in range(24):
            col = L(3 + j)
            if label == "Gross profit":
                v = f"={col}5-{col}6"
            elif label == "Total opex":
                v = f"=SUM({col}8:{col}13)"
            elif label == "EBITDA":
                v = f"={col}7-{col}14"
            else:
                v = round(base * (1 + g) ** (j // 12) * (1 + (0.02 * ((j % 12) in (9, 10, 11)) if label == "Revenue" else 0)), -2)
            c = ws.cell(row=r, column=3 + j, value=v)
            c.number_format = "#,##0"
        if base is None:
            for c in ws[r]:
                c.font = Font(bold=True)
    assert ws.cell(row=RENT_ROW, column=1).value == "Rent"
    wb.defined_names["RENT_FORECAST"] = DefinedName("RENT_FORECAST", attr_text=f"Forecast!$C${RENT_ROW}:$Z${RENT_ROW}")
    a = wb.create_sheet("Assumptions")
    header(a, ["assumption", "value", "source"], [34, 26, 60])
    for row in [("Revenue growth 2028", "+4%", "D. Wong email 14 Aug 2026"),
                ("Headcount", "18, flat", "D. Wong email 14 Aug 2026"),
                ("Rent 2027-2028", "HK$80,000/month flat", "Pending lease renewal; COMPANY.md; D. Wong email 14 Aug 2026"),
                ("FX", "USD 7.80, RMB 1.08", "fx_rates.xlsx")]:
        a.append(row)
    save_wb(wb, "sheets/forecast_2027_2028.xlsx", when)


# ----------------------------------------------------------------------------- ledger CSVs, text docs
def write_csv(rel, cols, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    w.writerows(rows)
    write(rel, buf.getvalue().encode())


def write_coa():
    write_csv("ledger/chart_of_accounts.csv", ["Code", "Name", "Type", "Report group", "Tax"],
              [(c, n, t, g, "Tax Exempt") for c, n, t, g in sorted(ACCOUNTS)])


def write_gl(until):
    write_csv("ledger/gl_export_2026.csv",
              ["Date", "Source", "Journal No.", "Reference", "Contact", "Description", "Account Code", "Account",
               "Debit", "Credit", "Net", "Tax Rate"],
              [(r["date"].isoformat(), r["source"], r["no"], r["ref"], r["contact"], r["desc"], r["code"], ACC[r["code"]][1],
                f"{r['dr']:.2f}" if r["dr"] else "", f"{r['cr']:.2f}" if r["cr"] else "", f"{r['dr'] - r['cr']:.2f}", "Tax Exempt")
               for r in GL if r["date"] <= until])


def write_payments(until):
    cols = list(PAYMENTS[0])
    write_csv("ledger/payments_history.csv", cols,
              [[p[c].isoformat() if isinstance(p[c], date) else (f"{p[c]:.2f}" if isinstance(p[c], float) else p[c])
                for c in cols] for p in sorted(PAYMENTS, key=lambda x: (x["payment_date"], x["supplier_id"])) if p["payment_date"] <= until])


def eml(rel, frm, to, subject, when, body, cc=None, extra=None):
    m = EmailMessage(policy=SMTPUTF8)
    m["From"], m["To"], m["Subject"] = frm, to, subject
    if cc:
        m["Cc"] = cc
    m["Date"] = when.strftime("%a, %d %b %Y %H:%M:%S +0800")
    m["Message-ID"] = f"<{hashlib.md5(subject.encode()).hexdigest()[:16]}@{frm.split('@')[1].rstrip('>')}>"
    for k, v in (extra or {}).items():
        m[k] = v
    m.set_content(body, cte="8bit")
    write(rel, m.as_bytes())


def company_md(with_forecast):
    sup = "\n".join(f"| {k} | {s['name_en']} {s['name_zh']} | {s['currency']} | {s['domain']} | {s['terms']} days | {s['contract']} |"
                    for k, s in SUP.items())
    fc = ("\n## Forecast assumptions (2027-2028)\n- Rent assumed flat at HK$80,000 in 2027 pending lease renewal (D. Wong, Aug 2026).\n"
          "- Revenue +4% p.a.; headcount flat at 18; FX USD 7.80, RMB 1.08.\n- Source: docs/emails/2026-08-14_david_forecast_assumptions.eml\n"
          if with_forecast else "")
    return f"""# COMPANY.md - {CO['name_en']} ({CO['name_zh']})

Hong Kong trading company, 18 staff. Imports electronic components from Shenzhen/Dongguan, resells to HK and SE Asia.
Functional currency HKD (also RMB, USD). FY = calendar year. BR No. {CO['br']}.
Office: {CO['addr_en']}. Warehouse: {CO['warehouse']}.
Bank: {CO['bank']} a/c {CO['bank_acct']}.

## People
- David Wong - Director / owner. Approves anything above HK$50,000.
- Anna Chan - Finance Manager. Month-end close, forecast, budget.
- Ken Lau - Accounts Clerk. Invoice entry, payments run.

## Conventions
- Xero-style account codes (ledger/chart_of_accounts.csv): 200 Sales, 310 COGS (all stock purchases), 425 Freight,
  469 Rent, 471 Building mgmt, 473 R&M, 445 Electricity, 485 Software. Facilities = 445 + 469 + 471 + 473.
- Invoice register: sheets/invoice_register.xlsx, one row per supplier invoice, amount_hkd = amount x month fx rate.
- Invoice PDFs filed under docs/invoices/YYYY-MM/; new ones arrive in docs/invoices/inbox/.

## Suppliers
| ID | Name | Ccy | Known domain | Terms | Contract |
|---|---|---|---|---|---|
{sup}

## Policies
- Price tolerance: invoice unit price may not exceed the contract price by more than 1%. Otherwise hold.
- Approval: any invoice or payment above HK$50,000 needs D. Wong's approval.
- Payments only to bank accounts on the supplier master. Bank changes need written confirmation by the
  supplier's authorised signatory plus a call-back to a known number. Email alone is never enough.
- Duplicates: never enter an invoice whose number or supplier+amount matches an existing entry.
{fc}"""


# ----------------------------------------------------------------------------- file/git plumbing
def write(rel, data):
    p = WS / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())


def git(*args, when=None, who="anna"):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
               GIT_DIR=str(GIT_DIR), GIT_WORK_TREE=str(WS))
    if when:
        name, mail, _ = PEOPLE[who]
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=mail, GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=mail,
                   GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    return subprocess.run(["git", *args], cwd=WS, env=env, check=True, capture_output=True, text=True).stdout.strip()


def commit(msg, when, who):
    git("add", "-A")
    git("commit", "-q", "-m", msg, when=when, who=who)
    return git("rev-parse", "HEAD")


def text_of(data, page=None):
    doc = fitz.open(stream=data, filetype="pdf")
    return "\n".join(doc[i].get_text() for i in (range(len(doc)) if page is None else [page]))


def find_page(data, needle):
    doc = fitz.open(stream=data, filetype="pdf")
    return next(i + 1 for i in range(len(doc)) if needle in doc[i].get_text().replace("\n", " "))


# ----------------------------------------------------------------------------- main
def main():
    if WS.exists():
        shutil.rmtree(WS)
    GIT_DIR.mkdir(parents=True)
    git("init", "-q", "-b", "main")
    git("config", "core.worktree", "../..")
    (GIT_DIR / "info").mkdir(exist_ok=True)
    (GIT_DIR / "info" / "exclude").write_text("/.trace/git/\n")

    # ---- render documents once
    pdfs = {}
    for inv in HIST + INBOX:
        b = RENDER[inv["sid"]](inv)
        pdfs[f"{inv['folder']}/{inv['file']}"] = scan(b, inv["no"]) if inv["file"] in SCANNED else b
        inv["clean_pdf"] = b
    contracts = {"docs/contracts/S01_supply_agreement_2026.pdf": supply_agreement("S01"),
                 "docs/contracts/S02_supply_agreement_2026.pdf": supply_agreement("S02"),
                 "docs/contracts/S03_freight_rate_card_2026.pdf": rate_card(),
                 "docs/contracts/S04_lease_2024_2026.pdf": lease(LEASE_OLD),
                 "docs/contracts/S05_clouddesk_order_form.pdf": order_form()}
    new_lease = lease(LEASE_NEW)
    sep_bank = [r for r in GL if r["code"] == "090" and r["date"].month == 9]
    opening = balance("090", D(2026, 8, 31))
    stmt_lines = [(r["date"], r["bank_desc"] or r["desc"].upper(), r2(r["dr"] - r["cr"])) for r in sep_bank]
    stmt_pdf, stmt_close = bank_statement(stmt_lines, opening)

    # ---- assertions
    for j in JOURNALS:
        assert abs(sum(l[1] - l[2] for l in j["lines"])) < 0.005, j
    assert abs(sum(r["dr"] - r["cr"] for r in GL)) < 0.005
    run = OPEN_CASH
    for r in sorted([r for r in GL if r["code"] == "090"], key=lambda r: (r["date"], r["no"])):
        run += r["dr"] - r["cr"]
        assert run > 0, "cash went negative"
    assert abs(stmt_close - balance("090", CLOSE)) < 0.005, "bank statement does not reconcile to GL"
    stmt_set = {(d, -a) for d, _, a in stmt_lines}
    for pmt in PAYMENTS:
        if pmt["payment_date"].month == 9 and pmt["payment_date"].year == 2026:
            assert (pmt["payment_date"], pmt["amount_hkd"]) in stmt_set, pmt
    s01 = [p for p in PAYMENTS if p["supplier_id"] == "S01"]
    assert len(s01) >= 6 and all(p["bank_account_paid"].endswith("2049") for p in s01)
    for row in reg_rows(CLOSE, CLOSE):
        inv = by_no[row[3]]
        assert row[5] == inv["total"] and money(inv["total"]) in text_of(inv["clean_pdf"]), row
        assert abs(r2(row[5] * row[6]) - row[7]) < 0.005
        assert inv["date"].weekday() < 5
        assert abs(inv["total"] - sum(q * u for _, _, q, u in inv["lines"])) < 0.005
    for inv in INBOX:
        assert money(inv["total"]) in text_of(inv["clean_pdf"]) and inv["date"].weekday() < 5
    assert "82,400" in text_of(new_lease, 2) and "4." in text_of(new_lease, 2) and len(fitz.open(stream=new_lease)) == 3

    # ---- staged history
    W = lambda s: datetime.fromisoformat(s)  # noqa: E731
    hashes = {}
    write(".gitignore", "ground_truth/\n~$*\n")
    write("COMPANY.md", company_md(False))
    write_coa()
    write_master(W("2026-01-09T10:12:00"))
    for k, v in contracts.items():
        write(k, v)
    write_fx("2026-01", W("2026-01-09T10:12:00"))
    hashes["setup"] = commit("Set up finance workspace: COMPANY.md, chart of accounts, supplier master, 2026 contracts",
                             "2026-01-09T10:12:00+08:00", "anna")
    write_bva(0, W("2026-01-23T16:40:00"))
    hashes["budget"] = commit("Budget 2026 approved (D. Wong, 20 Jan)", "2026-01-23T16:40:00+08:00", "anna")
    write_gl(D(2026, 6, 30))
    write_payments(D(2026, 6, 30))
    write_bva(6, W("2026-07-10T11:05:00"))
    write_fx("2026-07", W("2026-07-10T11:05:00"))
    hashes["h1"] = commit("H1 close: GL export Jan-Jun, payments history, budget vs actual to June",
                          "2026-07-10T11:05:00+08:00", "anna")

    def enter(until, when_s, msg, who, gl_until=None, bva_m=None, fx_m=None):
        when = W(when_s[:19])
        write_register(until, when.date(), when)
        for inv in HIST:
            if inv["date"] <= until:
                rel = f"{inv['folder']}/{inv['file']}"
                write(rel, pdfs[rel])
        if gl_until:
            write_gl(gl_until)
            write_payments(gl_until)
            write_bva(bva_m, when)
            write_fx(fx_m, when)
        return commit(msg, when_s, who)

    hashes["jul"] = enter(D(2026, 7, 31), "2026-08-05T15:20:00+08:00", "Enter July invoices; GL export to 31 Jul", "ken",
                          D(2026, 7, 31), 7, "2026-08")
    eml("docs/emails/2026-08-14_david_forecast_assumptions.eml", f"David Wong <{PEOPLE['david'][1]}>",
        f"Anna Chan <{PEOPLE['anna'][1]}>", "2027-28 forecast assumptions", datetime(2026, 8, 14, 9, 47),
        "Anna,\n\nFor the 2027-28 forecast please keep rent flat at HK$80,000/month in 2027 until the warehouse lease is renewed.\n"
        "Landlord hinted at an increase but nothing is agreed yet. Revenue +4% a year, headcount flat at 18.\n\nDavid\n")
    write("COMPANY.md", company_md(True))
    write_forecast(W("2026-08-14T17:30:00"))
    hashes["fc"] = commit("Forecast 2027-28 v1: rent flat pending lease renewal", "2026-08-14T17:30:00+08:00", "anna")
    hashes["aug"] = enter(D(2026, 8, 31), "2026-09-02T14:10:00+08:00", "Enter August invoices; GL export to 31 Aug", "ken",
                          D(2026, 8, 31), 8, "2026-09")
    hashes["sep1"] = enter(D(2026, 9, 3), "2026-09-03T11:45:00+08:00",
                           "Enter early September invoices (incl. Pacific Freight INV-2291)", "ken")
    hashes["sep2"] = enter(D(2026, 9, 18), "2026-09-18T16:00:00+08:00", "Enter mid-September invoices", "ken")
    write_register(CLOSE, CLOSE, W("2026-10-02T10:30:00"))
    write_gl(CLOSE)
    write_payments(CLOSE)
    write_bva(9, W("2026-10-02T10:30:00"))
    write_fx("2026-10", W("2026-10-02T10:30:00"))
    write("docs/bank/statement_2026-09.pdf", stmt_pdf)
    hashes["close"] = commit("September close (in progress): bank statement, payments run, GL export to 30 Sep",
                             "2026-10-02T10:30:00+08:00", "anna")

    # sidecar sources (backfilled for key historical cells)
    regs = reg_rows(CLOSE, CLOSE)
    rowno = {r[3]: i + 2 for i, r in enumerate(regs)}
    s01_jul = next(i for i in HIST if i["sid"] == "S01" and i["date"].month == 7)
    old_lease_p = find_page(contracts["docs/contracts/S04_lease_2024_2026.pdf"], "HK$80,000")
    s01_c = contracts["docs/contracts/S01_supply_agreement_2026.pdf"]
    sources = [
        dict(file="sheets/forecast_2027_2028.xlsx", sheet="Forecast", cell=f"C{RENT_ROW}:Z{RENT_ROW}", value=80000,
             sources=[dict(doc="COMPANY.md", page=None, quote="Rent assumed flat at HK$80,000 in 2027 pending lease renewal (D. Wong, Aug 2026)."),
                      dict(doc="docs/emails/2026-08-14_david_forecast_assumptions.eml", page=None,
                           quote="please keep rent flat at HK$80,000/month in 2027 until the warehouse lease is renewed"),
                      dict(doc="docs/contracts/S04_lease_2024_2026.pdf", page=old_lease_p,
                           quote="The monthly rent shall be HK$80,000 (Hong Kong Dollars Eighty Thousand) exclusive of rates and management fees, fixed for the whole Term.")],
             reason="Rent held flat at current lease rate until the lease expiring 31 Dec 2026 is renewed.", commit=hashes["fc"]),
        dict(file="sheets/invoice_register.xlsx", sheet="Register", cell=f"F{rowno['INV-2291']}", value=INV2291["total"],
             sources=[dict(doc=f"{INV2291['folder']}/{INV2291['file']}", page=1, quote=f"TOTAL HKD {money(INV2291['total'])}")],
             reason="Entered Pacific Freight INV-2291 (August/September trucking).", commit=hashes["sep1"]),
        dict(file="sheets/invoice_register.xlsx", sheet="Register", cell=f"F{rowno[s01_jul['no']]}", value=s01_jul["total"],
             sources=[dict(doc=f"{s01_jul['folder']}/{s01_jul['file']}", page=1, quote=f"价税合计 人民币（RMB） {money(s01_jul['total'])}"),
                      dict(doc="docs/contracts/S01_supply_agreement_2026.pdf", page=find_page(s01_c, "SP-4410"), quote="SP-4410 ... RMB 109.00")],
             reason="Entered Shenzhen Parts July invoice; unit prices match contract §4.2.", commit=hashes["jul"]),
        dict(file="sheets/supplier_master.xlsx", sheet="Suppliers", cell="F2", value=SUP["S01"]["bank_acct"],
             sources=[dict(doc="docs/contracts/S01_supply_agreement_2026.pdf", page=find_page(s01_c, "2049"),
                           quote=f"Seller's designated account ... account no. {SUP['S01']['bank_acct']}")],
             reason="Supplier bank account per signed 2026 supply agreement clause 5.2.", commit=hashes["setup"]),
        dict(file="sheets/budget_vs_actual_2026.xlsx", sheet="Budget monthly", cell="C" + str(PL_CODES.index("469") + 2), value=80000,
             sources=[dict(doc="docs/contracts/S04_lease_2024_2026.pdf", page=old_lease_p, quote="The monthly rent shall be HK$80,000")],
             reason="Budget 2026 rent = current lease rent.", commit=hashes["budget"]),
    ]
    write(".trace/sources.json", json.dumps(sources, indent=2, ensure_ascii=False) + "\n")
    hashes["src"] = commit("Backfill Trace source index for key cells", "2026-10-02T17:40:00+08:00", "anna")

    # ---- uncommitted demo material
    for inv in INBOX:
        rel = f"{inv['folder']}/{inv['file']}"
        write(rel, pdfs[rel])
    write("docs/contracts/S04_lease_2027_signed.pdf", new_lease)
    eml("docs/emails/2026-09-29_landlord_lease_signed.eml", "Raymond Ho <raymond.ho@kbproperties.com.hk>",
        f"Anna Chan <{PEOPLE['anna'][1]}>", "Countersigned tenancy agreement - Unit 9A, 2027-2029", datetime(2026, 9, 29, 16, 12),
        "Dear Anna,\n\nPlease find attached the countersigned tenancy agreement for Unit 9A for 1 Jan 2027 - 31 Dec 2029.\n"
        "Rent and the annual review are set out in clause 4. The original will follow by courier.\n\nBest regards,\nRaymond Ho\nKowloon Bay Properties Ltd\n",
        cc=f"David Wong <{PEOPLE['david'][1]}>", extra={"X-Attachment": "S04_lease_2027_signed.pdf (saved to docs/contracts/)"})
    eml("docs/emails/2026-10-02_shenzhenparts_bank_change.eml", f"Shenzhen Parts Accounts <accounts@{FAKE_DOMAIN}>",
        f"Harbour Lane Accounts <{PEOPLE['ken'][1]}>", "Updated bank details / 银行账户变更通知 - URGENT", datetime(2026, 10, 2, 8, 55),
        "Dear Harbour Lane accounts team,\n\nPlease note our company bank account has changed. Please pay invoice SP-2026-0917\n"
        f"and all future invoices to the new account: {NEW_BANK[0]}, account no. {NEW_BANK[1]}.\n"
        "请将款项汇入以上新账户，旧账户已停止使用。Kindly process this week.\n\nLily Zhang 张丽\nAccounts Dept, Shenzhen Parts Co., Ltd.\n",
        extra={"X-Attachment": "scan_1002.pdf (saved to docs/invoices/inbox/)"})

    # ---- ground truth
    s01_in, s02_in, dup_in, s03_in, s05_in = INBOX
    last6 = s01[-6:]

    def reg_row(inv, status, controls=()):
        f = fx(inv["currency"], inv["date"])
        return dict(date=inv["date"].isoformat(), supplier_id=inv["sid"], supplier=SUP[inv["sid"]]["name_en"], invoice_no=inv["no"],
                    currency=inv["currency"], amount=inv["total"], fx_rate=f, amount_hkd=r2(inv["total"] * f),
                    account_code=inv["account"], due_date=inv["due"].isoformat(), status=status,
                    source_file=f"{inv['folder']}/{inv['file']}", needs_director_approval=r2(inv["total"] * f) > 50000,
                    controls_fired=list(controls))

    p42 = find_page(s01_c, "SP-4410")
    fac = {c: dict(budget=sum(budget(c, m) for m in range(1, 10)), actual=r2(sum(actual(c, m) for m in range(1, 10)))) for c in ("445", "469", "471", "473")}
    for v in fac.values():
        v["variance"] = r2(v["actual"] - v["budget"])
    rm_small = r2(sum(actual("473", m) for m in range(1, 10)) - 38500 - 9800)
    drivers = [
        dict(driver="Temporary storage licence Unit 3C (Kowloon Bay Properties), Aug + Sep 2026", account="469", amount=24000.0,
             refs=["KBP/L/2608", "KBP/L/2609"]),
        dict(driver="Emergency air-con compressor replacement, warehouse (Arctic Breeze Engineering), 14 Jul 2026", account="473", amount=38500.0),
        dict(driver="Pallet racking repair after safety inspection (Steelform Racking), 16 Sep 2026", account="473", amount=9800.0),
        dict(driver="Building management fee revised HK$6,800 -> HK$8,000/month from Jun 2026", account="471", amount=4800.0),
        dict(driver="Summer electricity above budget (Jun-Sep), partly offset by lower Jan-May", account="445", amount=fac["445"]["variance"]),
        dict(driver="Routine small repairs vs HK$2,000/month budget", account="473", amount=r2(rm_small - 18000)),
    ]
    expected = dict(
        as_of=TODAY.isoformat(),
        planted_problems=[
            dict(id="P1", control="PRICE-001", invoice_file=f"docs/invoices/inbox/{s01_in['file']}", invoice_no=s01_in["no"], supplier_id="S01",
                 evidence=dict(item="SP-4410", invoice_unit_price=118.0, contract_unit_price=109.0, currency="RMB",
                               pct_over=round((118 - 109) / 109 * 100, 2), tolerance_pct=1.0, qty=2000, overcharge_rmb=18000.0,
                               contract_ref=dict(doc="docs/contracts/S01_supply_agreement_2026.pdf", page=p42, clause="4.2"))),
            dict(id="P2", control="BANK-001", invoice_file=f"docs/invoices/inbox/{s01_in['file']}", invoice_no=s01_in["no"], supplier_id="S01",
                 evidence=dict(invoice_bank_account=NEW_BANK[1], invoice_last4="7731", master_bank_account=SUP["S01"]["bank_acct"],
                               master_last4="2049", last_6_payments=[dict(date=p["payment_date"].isoformat(), invoice_no=p["invoice_no"],
                                                                          amount=p["amount"], account=p["bank_account_paid"]) for p in last6],
                               email="docs/emails/2026-10-02_shenzhenparts_bank_change.eml",
                               contract_clause=dict(doc="docs/contracts/S01_supply_agreement_2026.pdf", page=find_page(s01_c, "5.3"), clause="5.3"))),
            dict(id="P3", control="DOMAIN-001", invoice_file=f"docs/invoices/inbox/{s01_in['file']}", invoice_no=s01_in["no"], supplier_id="S01",
                 evidence=dict(sender_domain=FAKE_DOMAIN, known_domain=SUP["S01"]["domain"],
                               email="docs/emails/2026-10-02_shenzhenparts_bank_change.eml", invoice_contact_email=f"accounts@{FAKE_DOMAIN}")),
            dict(id="P4", control="DUP-001", invoice_file=f"docs/invoices/inbox/{dup_in['file']}", invoice_no=dup_in["no"], supplier_id="S03",
                 evidence=dict(matches_invoice_no="INV-2291", original_date=INV2291["date"].isoformat(), entered="2026-09-03",
                               amount=INV2291["total"], currency="HKD", register_row=rowno["INV-2291"],
                               original_status="Approved (due 2026-10-01, unpaid)")),
        ],
        clean_invoices=[f"docs/invoices/inbox/{i['file']}" for i in (s02_in, s03_in, s05_in)],
        tasks=[
            dict(id=1, prompt="We signed the new warehouse lease. Update the forecast.",
                 expected=dict(file="sheets/forecast_2027_2028.xlsx", named_range="RENT_FORECAST", sheet="Forecast",
                               cells={f"{__import__('openpyxl').utils.get_column_letter(3 + j)}{RENT_ROW}": (82400.0 if j < 12 else 84872.0) for j in range(24)},
                               changed_cells=24, source=dict(doc="docs/contracts/S04_lease_2027_signed.pdf", page=3, clause="4"),
                               also=["COMPANY.md rent assumption should be updated (lease renewed, +3%/yr)",
                                     "supplier_master S04 contract_file -> S04_lease_2027_signed.pdf"])),
            dict(id=2, prompt="Enter this week's supplier invoices.",
                 expected=dict(rows=[reg_row(s02_in, "Entered"), reg_row(s03_in, "Entered"), reg_row(s05_in, "Entered"),
                                     reg_row(s01_in, "HELD", ["PRICE-001", "BANK-001", "DOMAIN-001"]), reg_row(dup_in, "HELD", ["DUP-001"])])),
            dict(id=3, prompt="Why is 2027 rent 82,400?",
                 expected=dict(facts=["New tenancy agreement KBP/L/2027/09A signed 29 Sep 2026 with Kowloon Bay Properties",
                                      "Clause 4.1 (page 3): rent HK$82,400/month from 1 Jan 2027",
                                      "Clause 4.2: +3% every 1 January (HK$84,872 in 2028)",
                                      "Previously HK$80,000 flat: old lease (expires 31 Dec 2026) and COMPANY.md assumption by D. Wong, Aug 2026",
                                      "Increase vs prior forecast: +HK$2,400/month (+3.0%)"],
                               sources=[dict(doc="docs/contracts/S04_lease_2027_signed.pdf", page=3, clause="4"),
                                        dict(doc="docs/emails/2026-09-29_landlord_lease_signed.eml"),
                                        dict(doc="COMPANY.md"), dict(doc="docs/emails/2026-08-14_david_forecast_assumptions.eml"),
                                        dict(commit=hashes["fc"], note="forecast v1 rent flat")])),
            dict(id=4, prompt="Which contracts need action in the next 30 days?",
                 expected=dict(items=[dict(contract="docs/contracts/S05_clouddesk_order_form.pdf", supplier_id="S05",
                                           renewal_date="2026-11-16", notice_days=30, notice_deadline="2026-10-17",
                                           commitment_if_missed="12 months x USD 1,450 = USD 17,400")],
                               not_in_window=["S04 old lease expires 2026-12-31 (already replaced by new lease)",
                                              "S01/S02 supply agreements expire 2026-12-31"])),
            dict(id=5, prompt="Why is Facilities over budget YTD?",
                 expected=dict(period="Jan-Sep 2026", accounts=fac,
                               facilities_budget=sum(v["budget"] for v in fac.values()),
                               facilities_actual=r2(sum(v["actual"] for v in fac.values())),
                               facilities_variance=r2(sum(v["variance"] for v in fac.values())), drivers=drivers)),
        ],
    )
    write("ground_truth/expected.json", json.dumps(expected, indent=2, ensure_ascii=False) + "\n")

    # ---- re-read checks on written files
    wb = load_workbook(WS / "sheets/budget_vs_actual_2026.xlsx")
    gl_sum = {}
    with open(WS / "ledger/gl_export_2026.csv") as f:
        for r in csv.DictReader(f):
            gl_sum[r["Account Code"]] = gl_sum.get(r["Account Code"], 0) + float(r["Net"])
    for row in wb["YTD"].iter_rows(min_row=5, max_row=4 + len(PL_CODES), values_only=True):
        g = gl_sum.get(row[0], 0) * (-1 if ACC[row[0]][3] == "Revenue" else 1)
        assert abs(g - row[4]) < 0.01, (row, g)
    wbr = load_workbook(WS / "sheets/invoice_register.xlsx")["Register"]
    assert abs(sum(r[5] for r in wbr.iter_rows(min_row=2, values_only=True)) - sum(i["total"] for i in HIST)) < 0.01

    # ---- summary
    print("workspace/ generated")
    for d in sorted({p.parent for p in WS.rglob("*") if p.is_file() and GIT_DIR not in p.parents}):
        files = sorted(f.name for f in d.iterdir() if f.is_file())
        print(f"  {d.relative_to(WS)}/  ({len(files)} files)")
    print(f"GL rows {len(GL)} ({len(JOURNALS)} journals); register rows {len(HIST)}; payments {len(PAYMENTS)}; "
          f"Sep bank lines {len(stmt_lines)}; opening {money(opening)} closing {money(stmt_close)}")
    for code in ("425", "445", "469", "471", "473"):
        b = sum(budget(code, m) for m in range(1, 10))
        a = sum(actual(code, m) for m in range(1, 10))
        print(f"  {code} {ACC[code][1]:<28} budget {b:>10,.0f} actual {a:>12,.2f} var {a - b:>+10,.0f}")
    print(git("log", "--format=%h %ad %an  %s", "--date=short"))
    print(git("status", "--short"))


if __name__ == "__main__":
    main()
