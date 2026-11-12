"""Seeded synthetic Indian document dataset with labelled PII spans (stdlib only).

    python dataset/generate_dataset.py            # writes dataset/<category>/*.txt + dataset/ground_truth.json

50 documents: loan 15, kyc 15, support 10, insurance 10 (5 of them negatives with no PII).
Every value is synthetic. Entity offsets are recorded at insertion time and verified
(text[start:end] == value) before anything is written. Same seed -> byte-identical output.

Coverage on purpose: labelled forms AND free-text prose, repeated mentions, first-name-only
re-mentions, two people sharing a surname, Hinglish (~20-25%), honorifics, initials, a lowercase
chat name, multi-line forms, and negatives full of numbers / role words / bank codes.

Checksums are implemented here independently of the backend so the dataset does not grade the
detector with the detector's own code.
"""
import json
import random
import re
import shutil
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parent
CATEGORIES = {"loan": 15, "kyc": 15, "support": 10, "insurance": 10}

# ---------------------------------------------------------------- value pools (synthetic)
FIRST = {
    "M": ["Rahul", "Arjun", "Vikram", "Suresh", "Ramesh", "Imran", "Venkatesh", "Harpreet", "Anil", "Sanjay",
          "Karthik", "Abhishek", "Mohammed", "Pranav", "Rohit", "Siddharth", "Gopal", "Naveen", "Deepak", "Joseph",
          "Aniket", "Farhan", "Manoj", "Tushar", "Rajesh", "Ashok", "Nikhil", "Yusuf", "Bhavesh", "Dinesh"],
    "F": ["Priya", "Kavitha", "Lakshmi", "Ananya", "Sneha", "Fatima", "Meera", "Pooja", "Deepika", "Asha",
          "Neha", "Shalini", "Gurpreet", "Ritu", "Swati", "Nandini", "Ayesha", "Divya", "Sunita", "Mary",
          "Anjali", "Rekha", "Shruti", "Zoya", "Bhavna", "Kiran", "Revathi", "Madhuri", "Tanvi", "Usha"],
}
LAST = ["Sharma", "Nair", "Patil", "Iyer", "Reddy", "Khan", "Singh", "Gupta", "Deshmukh", "Banerjee",
        "Subramaniam", "Menon", "Kulkarni", "Chatterjee", "Joshi", "Verma", "Pillai", "Shaikh", "Rao", "Mehta",
        "Agarwal", "Naidu", "Gill", "Fernandes", "Mishra", "Pandey", "Bhat", "Hegde", "Saxena", "Chauhan",
        "Thakur", "Mukherjee", "Desai", "Kapoor", "Bose", "Yadav", "Ansari", "D'Souza", "Kamath", "Sethi"]
CITIES = [  # city, pin prefix, GST state code, localities, streets
    ("Pune", "411", "27", ["Shivaji Nagar", "Kothrud", "Aundh", "Hadapsar"], ["FC Road", "Karve Road", "Baner Road"]),
    ("Mumbai", "400", "27", ["Andheri West", "Dadar East", "Powai", "Borivali"], ["SV Road", "Link Road", "LBS Marg"]),
    ("Bengaluru", "560", "29", ["Indiranagar", "Koramangala", "Basavanagudi", "Whitefield"], ["100 Feet Road", "Bull Temple Road", "ITPL Main Road"]),
    ("Hyderabad", "500", "36", ["Kondapur", "Banjara Hills", "Kukatpally", "Gachibowli"], ["Road No. 12", "JNTU Road", "Botanical Garden Road"]),
    ("Chennai", "600", "33", ["Anna Nagar", "Adyar", "T Nagar", "Velachery"], ["2nd Avenue", "LB Road", "Usman Road"]),
    ("Kolkata", "700", "19", ["Salt Lake", "Ballygunge", "Behala", "Dum Dum"], ["Sector V", "Gariahat Road", "Diamond Harbour Road"]),
    ("Delhi", "110", "07", ["Karol Bagh", "Lajpat Nagar", "Dwarka", "Rohini"], ["Arya Samaj Road", "Ring Road", "Sector 10 Road"]),
    ("Lucknow", "226", "09", ["Gomti Nagar", "Aliganj", "Indira Nagar"], ["Vibhuti Khand", "Kapoorthala Road"]),
    ("Ahmedabad", "380", "24", ["Navrangpura", "Satellite", "Maninagar"], ["CG Road", "SG Highway"]),
    ("Kochi", "682", "32", ["Kakkanad", "Edappally", "Fort Kochi"], ["MG Road", "Seaport Airport Road"]),
    ("Noida", "201", "09", ["Sector 22", "Sector 62", "Sector 18"], ["Main Road", "Film City Road"]),
    ("Davangere", "577", "29", ["PJ Extension", "Vidyanagar", "Nittuvalli"], ["Hadadi Road", "Shamanur Road"]),
]
BANKS = ["HDFC Bank", "State Bank of India", "ICICI Bank", "Canara Bank", "Axis Bank"]
JOBS = ["software engineer", "school teacher", "shop owner", "nurse", "civil contractor", "accountant"]
HOSPITALS = ["Sunrise Multispeciality Hospital", "City Care Hospital", "Lifeline Nursing Home"]
RELATIONS = ["wife", "son", "daughter", "mother", "father"]
COMPANIES = ["Shree Ganesh Traders", "Bright Future Enterprises", "Annapurna Foods", "Metro Hardware Mart"]

# ---------------------------------------------------------------- checksums (independent implementation)
_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def verhoeff_digit(num: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def gstin_check(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _B36.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _B36[(36 - total % 36) % 36]


# ---------------------------------------------------------------- generators
class Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.n_aadhaar = 0

    def letters(self, n):
        return "".join(self.r.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(n))

    def digits(self, n, first_nonzero=False):
        d = "".join(self.r.choice("0123456789") for _ in range(n))
        return (self.r.choice("123456789") + d[1:]) if first_nonzero else d

    def aadhaar(self):
        self.n_aadhaar += 1
        body = self.r.choice("23456789") + self.digits(10)
        # half Verhoeff-valid, half arbitrary (synthetic demo IDs must still be masked)
        num = body + (verhoeff_digit(body) if self.n_aadhaar % 2 else self.r.choice("0123456789"))
        style = self.r.choice(["space", "space", "dash", "plain"])
        if style == "plain":
            return num
        sep = " " if style == "space" else "-"
        return sep.join([num[:4], num[4:8], num[8:]])

    def pan(self, surname="", holder="P"):
        fifth = (surname[:1] or self.letters(1)).upper()
        return self.letters(3) + holder + fifth + self.digits(4) + self.letters(1)

    def gstin(self, state_code):
        p = self.pan(holder=self.r.choice("CF"))
        first14 = state_code + p + self.r.choice("123456789") + "Z"
        return first14 + gstin_check(first14)

    def voter(self):
        return self.letters(3) + self.digits(7)

    def passport(self):
        return self.r.choice("ABCDEFGHJKLMNPRSTUVW") + self.digits(7, first_nonzero=True)

    def city(self):
        return self.r.choice(CITIES)

    def address(self, city):
        name, pin3, _, locs, streets = city
        pin = pin3 + self.digits(3)
        loc, street = self.r.choice(locs), self.r.choice(streets)
        form = self.r.randrange(4)
        if form == 0:
            return f"Flat {self.r.randint(101, 1204)}, {self.r.choice(['Sai', 'Shanti', 'Green', 'Lotus'])} Residency, {loc}, {name} - {pin}"
        if form == 1:
            return f"{self.r.randint(1, 250)} {street}, {loc}, {name} {pin}"
        if form == 2:
            return f"H.No. {self.r.randint(1, 9)}-{self.r.randint(1, 30)}-{self.r.randint(1, 99)}, {loc}, {name} {pin}"
        return f"Plot {self.r.randint(1, 99)}, {street}, {name}, PIN {pin}"


# ---------------------------------------------------------------- templates
# [[TYPE:key]] marks an entity; {var} marks a non-PII filler. Person keys: pN full name, pNf first name,
# pNi initial form ("K. Ramesh"), pNl lowercase full name. Address keys: a1 full address, c1 city/locality.
# meta: genders per person, `shared` = person pairs that share a surname.
T = {
    "loan": [
        ({"p1": "M"}, "LOAN APPLICATION FORM\nApplicant Name: [[PERSON:p1]]\nPAN: [[PAN:pan1]]\nAadhaar: [[AADHAAR:aad1]]\n"
         "Voter ID: [[VOTER_ID:voter1]]\nResidential Address: [[ADDRESS:a1]]\nLoan Amount: Rs {amount}\nTenure: {tenure} months\nPurpose: {purpose}\n"),
        ({"p1": "F", "p2": "M", "shared": [("p1", "p2")]},
         "Home loan request {ref}. [[PERSON:p1]] and her husband [[PERSON:p2]] visited the {bank} branch on {date} to apply "
         "for a joint home loan of Rs {amount}. [[PERSON:p1f]] submitted her PAN [[PAN:pan1]] and [[PERSON:p2f]] submitted "
         "Aadhaar [[AADHAAR:aad2]]. The couple currently lives at [[ADDRESS:a1]]."),
        ({"p1": "M", "p2": "F"}, "MSME Business Loan - {company}\nProprietor: [[PERSON:p1]]\nGSTIN: [[GSTIN:gst1]]\n"
         "Proprietor PAN: [[PAN:pan1]]\nBusiness address: [[ADDRESS:a1]]\nAnnual turnover: Rs {turnover}\n"
         "Guarantor: [[PERSON:p2]] (Voter ID [[VOTER_ID:voter1]])\n"),
        ({"p1": "M"}, "Sir, mera naam [[PERSON:p1]] hai aur mujhe Rs {amount} ka personal loan chahiye. Main [[ADDRESS:c1]] "
         "mein rehta hoon. Mera PAN [[PAN:pan1]] hai aur Aadhaar [[AADHAAR:aad1]] hai. [[PERSON:p1f]] ki salary Rs {salary} "
         "per month hai."),
        ({"p1": "F", "p2": "M"}, "Credit officer note: Met [[PERSON:p1]] today regarding loan account {acct}. [[PERSON:p1f]] "
         "works as a {job} in [[ADDRESS:c1]] and wants to top up the loan. Co-applicant [[PERSON:p2]] was not present. "
         "Documents verified: PAN [[PAN:pan1]], passport [[PASSPORT:pass1]]."),
        # messy chat: all lowercase, spelling variant "reheta", spaced PAN
        ({"p1": "M"}, "sir mera naam [[PERSON:p1l]] hai, me [[ADDRESS:c1l]] me reheta hu. pan = [[PAN:pan1s]] hai, "
         "loan chahiye Rs {amount}"),
    ],
    "kyc": [
        ({"p1": "F", "p2": "M", "p3": "M", "shared": [("p1", "p2")]},
         "KYC FORM\nName: [[PERSON:p1]]\nFather's Name: [[PERSON:p2]]\nDOB: {dob}\nAadhaar No: [[AADHAAR:aad1]]\n"
         "PAN: [[PAN:pan1]]\nVoter ID: [[VOTER_ID:voter1]]\nAddress: [[ADDRESS:a1]]\nNominee: [[PERSON:p3]] ({relation_m})\n"),
        ({"p1": "M"}, "Dear Customer, this is to confirm that the re-KYC for [[PERSON:p1]] has been completed. The following "
         "documents were verified: Voter ID [[VOTER_ID:voter1]], Passport [[PASSPORT:pass1]]. Updated correspondence address: "
         "[[ADDRESS:a1]]. Please contact the branch if [[PERSON:p1f]] wishes to change the nominee."),
        ({"p1": "F"}, "Video KYC transcript\nAgent: Aapka poora naam bataiye.\nCustomer: Mera naam [[PERSON:p1]] hai.\n"
         "Agent: Aadhaar number?\nCustomer: [[AADHAAR:aad1]]\nAgent: Aur PAN?\nCustomer: [[PAN:pan1]]\n"
         "Agent: Aap kahan rehti hain?\nCustomer: [[ADDRESS:a1]]\nAgent: Dhanyavaad [[PERSON:p1f]] ji."),
        ({"p1": "F", "p2": "M", "shared": [("p1", "p2")]},
         "Joint account opening: Primary holder Smt. [[PERSON:p1]], secondary holder Shri [[PERSON:p2]]. PAN of primary "
         "holder [[PAN:pan1]], PAN of secondary holder [[PAN:pan2]]. Both reside at [[ADDRESS:a1]]."),
        ({"p1": "M"}, "Account holder [[PERSON:p1i]] (Aadhaar [[AADHAAR:aad1]]) requested an address change to [[ADDRESS:a1]]. "
         "Passport [[PASSPORT:pass1]] was submitted as proof of address."),
        # key=value export with a dotted Aadhaar and an abbreviated label
        ({"p1": "F"}, "kyc_export: name=[[PERSON:p1]]; a.id=[[AADHAAR:aad1d]]; pan=[[PAN:pan1]]; city=[[ADDRESS:c1]]; "
         "status=verified"),
    ],
    "support": [
        ({"p1": "M"}, "Ticket #{ticket}\nFrom: [[PERSON:p1]]\nSubject: EMI debited twice\nHi team, my EMI was debited twice "
         "this month. My PAN is [[PAN:pan1]] and my shop GSTIN is [[GSTIN:gst1]]. Please refund the extra amount.\n- [[PERSON:p1f]]"),
        ({"p1": "M"}, "Chat transcript {ticket}\nUser: hello, [[PERSON:p1l]] here. mera card block ho gaya hai\n"
         "Bot: Please share your registered PAN.\nUser: [[PAN:pan1]]\nUser: aur mera address [[ADDRESS:c1]] hai"),
        ({"p1": "F", "p2": "M"}, "Yesterday [[PERSON:p1]] raised a complaint that the branch at [[ADDRESS:c1]] refused to "
         "update her Aadhaar [[AADHAAR:aad1]]. Her brother [[PERSON:p2]] also holds an account with us. [[PERSON:p1f]] has "
         "asked for a callback."),
        # raw JSON payload from an order/support system (braces doubled for str.format)
        ({"p1": "M"}, '{{"ticket": "{ticket}", "customer_name": "[[PERSON:p1l]]", "address": "[[ADDRESS:a1]]", '
         '"pan": "[[PAN:pan1]]", "issue": "refund not received"}}'),
    ],
    "insurance": [
        ({"p1": "M", "p2": "F"}, "HEALTH INSURANCE CLAIM\nPolicy No: {policy}\nInsured: [[PERSON:p1]]\nPatient: [[PERSON:p2]] "
         "({relation_f})\nHospital: {hospital}, [[ADDRESS:c1]]\nClaim amount: Rs {amount}\nInsured PAN: [[PAN:pan1]]\n"
         "Insured Aadhaar: [[AADHAAR:aad1]]\nEmployer GSTIN (group policy): [[GSTIN:gst1]]\n"),
        ({"p1": "M", "p2": "F"}, "Motor claim {claim}: The policyholder [[PERSON:p1]] reported that the car met with an "
         "accident near [[ADDRESS:c1]] on {date}. The surveyor spoke to [[PERSON:p1f]] and to the witness [[PERSON:p2]]. "
         "Claimant address: [[ADDRESS:a1]]. Passport [[PASSPORT:pass1]] was given as ID."),
        ({"p1": "M", "p2": "F", "shared": [("p1", "p2")]},
         "Mere pati [[PERSON:p1]] ka {date} ko dehant ho gaya. Main [[PERSON:p2]], nominee, claim file kar rahi hoon. "
         "Policy {policy} hai. Hamara pata hai [[ADDRESS:a1]]. Mera Aadhaar [[AADHAAR:aad2]] hai."),
    ],
}
NEGATIVES = {
    "support": [
        "Ticket #{ticket}: The mobile app crashes when opening the statements page. Affected version 4.2.1. Customer "
        "reports the issue since {date}. Account ending XXXX{last4}. Priority: medium. Assigned to the digital banking team.",
        "Ticket #{ticket}: Customer asked about the interest rate on fixed deposits for 444 days. Current rate 7.25%. "
        "IFSC HDFC0001234 shared. No further action needed.",
        "Ticket #{ticket}: Branch ATM at the main market is out of cash. Reported by the branch manager at 10:45 AM. Cash "
        "replenishment scheduled with vendor ref VND-{n}.",
    ],
    "insurance": [
        "Claim {claim}: Windshield replacement approved for Rs {amount}. Garage invoice verified. Deductible of Rs 1,000 "
        "applied. Payment will be released in 3 working days.",
        "Policy renewal reminder: Policy {policy} is due for renewal on {date}. Premium Rs {amount}. Renew online to keep "
        "the no-claim bonus.",
    ],
}
_MARK = re.compile(r"\[\[([A-Z_]+):([a-z0-9]+)\]\]")


def fillers(g: Gen) -> dict:
    r = g.r
    return {
        "amount": f"{r.randint(1, 49)},{r.randint(10, 99)},000", "tenure": r.choice([12, 24, 36, 60, 120, 240]),
        "purpose": r.choice(["home renovation", "child education", "medical expenses", "working capital"]),
        "ref": f"HL/{r.randint(2024, 2026)}/{r.randint(1000, 9999)}", "bank": r.choice(BANKS),
        "date": f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}/{r.randint(2024, 2026)}",
        "company": r.choice(COMPANIES), "turnover": f"{r.randint(20, 99)},{r.randint(10, 99)},000",
        "salary": f"{r.randint(18, 95)},000", "acct": f"LN{r.randint(10 ** 7, 10 ** 8 - 1)}", "job": r.choice(JOBS),
        "dob": f"{r.randint(1, 28):02d}-{r.randint(1, 12):02d}-{r.randint(1960, 2002)}", "relation_m": r.choice(["husband", "son", "father", "brother"]),
        "relation_f": r.choice(["wife", "daughter", "mother", "sister"]),
        "ticket": f"TKT-{r.randint(10000, 99999)}", "policy": f"POL/{r.randint(2023, 2026)}/{r.randint(10000, 99999)}",
        "hospital": r.choice(HOSPITALS), "claim": f"CLM-{r.randint(100000, 999999)}", "last4": f"{r.randint(1000, 9999)}",
        "n": r.randint(100, 999),
    }


def make_values(g: Gen, meta: dict) -> dict:
    r = g.r
    vals, used_first, surnames = {}, set(), {}
    persons = [k for k in meta if k.startswith("p")]
    for k in persons:
        surnames[k] = r.choice(LAST)
    for a, b in meta.get("shared", []):
        surnames[b] = surnames[a]
    for k in persons:
        first = r.choice([f for f in FIRST[meta[k]] if f not in used_first])
        used_first.add(first)
        full = f"{first} {surnames[k]}"
        vals.update({k: full, k + "f": first, k + "l": full.lower(), k + "i": f"{r.choice('KMSRV')}. {first}"})
    city = g.city()
    loc = r.choice(city[3])
    vals["a1"] = g.address(city)
    vals["c1"] = r.choice([city[0], f"{loc}, {city[0]}"])
    vals["aad1"], vals["aad2"] = g.aadhaar(), g.aadhaar()
    vals["pan1"] = g.pan(surnames.get("p1", ""))
    vals["pan2"] = g.pan(surnames.get("p2", ""))
    vals["gst1"] = g.gstin(city[2])
    vals["voter1"], vals["pass1"] = g.voter(), g.passport()
    # Messy-format variants (added after the 12 Nov teammate review). Derived from the values above
    # WITHOUT drawing new random numbers, so documents generated before this change stay identical.
    vals["c1l"] = vals["c1"].lower()
    digits = re.sub(r"\D", "", vals["aad1"])
    vals["aad1d"] = ".".join([digits[:4], digits[4:8], digits[8:]])
    vals["pan1s"] = f"{vals['pan1'][:5]} {vals['pan1'][5:9]} {vals['pan1'][9]}"
    return vals


def render(template: str, vals: dict, fill: dict):
    """Fill fillers, then entities; record offsets while building the string."""
    template = template.format_map(fill)
    out, ents, pos = [], [], 0
    cur = 0
    for m in _MARK.finditer(template):
        out.append(template[pos:m.start()])
        cur += m.start() - pos
        value = vals[m.group(2)]
        # ref = which person / ID this mention belongs to (p1, p1f and p1i are the same person);
        # lets the evaluation detect a placeholder that merged two different people
        ents.append({"text": value, "type": m.group(1), "start": cur, "end": cur + len(value),
                     "ref": re.sub(r"^(p\d)[fil]$", r"\1", m.group(2))})
        out.append(value)
        cur += len(value)
        pos = m.end()
    out.append(template[pos:])
    text = "".join(out)
    for e in ents:
        assert text[e["start"]:e["end"]] == e["text"], e
    return text, ents


def generate(seed: int = SEED) -> list:
    g = Gen(seed)
    docs = []
    for cat, count in CATEGORIES.items():
        templates, negatives = T[cat], NEGATIVES.get(cat, [])
        n_pos = count - len(negatives)
        for i in range(count):
            fill = fillers(g)
            if i < n_pos:
                meta, tpl = templates[i % len(templates)]
                text, ents = render(tpl, make_values(g, meta), fill)
            else:
                text, ents = render(negatives[i - n_pos], {}, fill)
            docs.append({"document_id": f"{cat}_{i + 1:02d}", "category": cat, "text": text, "entities": ents,
                         "hinglish": bool(re.search(r"\b(mera|naam|hai|rehta|rehti|kahan|ki|ka|pati)\b", text))})
    return docs


def main() -> None:
    docs = generate()
    for cat in CATEGORIES:
        shutil.rmtree(ROOT / cat, ignore_errors=True)
        (ROOT / cat).mkdir(parents=True)
    for d in docs:
        (ROOT / d["category"] / f"{d['document_id']}.txt").write_text(d["text"], encoding="utf-8", newline="\n")
    (ROOT / "ground_truth.json").write_text(json.dumps({"seed": SEED, "documents": docs}, indent=2, ensure_ascii=False)
                                            + "\n", encoding="utf-8", newline="\n")
    n_ent = sum(len(d["entities"]) for d in docs)
    by_type = {}
    for d in docs:
        for e in d["entities"]:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    print(f"{len(docs)} documents, {n_ent} labelled entities, "
          f"{sum(d['hinglish'] for d in docs)} Hinglish, {sum(not d['entities'] for d in docs)} negatives")
    print("per type:", dict(sorted(by_type.items())))


if __name__ == "__main__":
    main()
