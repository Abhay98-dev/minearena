"""Dependency-free gazetteer for contextual Indian city/state detection.

The city catalogue covers state capitals, major urban centres and a wide set of district
headquarters/tier-2 cities. GLiNER remains the long-tail location detector when enabled.
Names are only emitted from location-bearing contexts, never from a bare mention.
"""
import re
from typing import List

from ..schemas import Span


STATE_ALIASES = {
    "Andhra Pradesh": ("andhra pradesh", "ap"),
    "Arunachal Pradesh": ("arunachal pradesh",),
    "Assam": ("assam",),
    "Bihar": ("bihar",),
    "Chhattisgarh": ("chhattisgarh", "chattisgarh"),
    "Goa": ("goa",),
    "Gujarat": ("gujarat",),
    "Haryana": ("haryana",),
    "Himachal Pradesh": ("himachal pradesh", "hp"),
    "Jharkhand": ("jharkhand",),
    "Karnataka": ("karnataka",),
    "Kerala": ("kerala",),
    "Madhya Pradesh": ("madhya pradesh", "mp"),
    "Maharashtra": ("maharashtra",),
    "Manipur": ("manipur",),
    "Meghalaya": ("meghalaya",),
    "Mizoram": ("mizoram",),
    "Nagaland": ("nagaland",),
    "Odisha": ("odisha", "orissa"),
    "Punjab": ("punjab",),
    "Rajasthan": ("rajasthan",),
    "Sikkim": ("sikkim",),
    "Tamil Nadu": ("tamil nadu", "tn"),
    "Telangana": ("telangana",),
    "Tripura": ("tripura",),
    "Uttar Pradesh": ("uttar pradesh", "up"),
    "Uttarakhand": ("uttarakhand", "uttaranchal"),
    "West Bengal": ("west bengal", "wb"),
    "Andaman and Nicobar Islands": ("andaman and nicobar islands", "andaman & nicobar islands"),
    "Chandigarh": ("chandigarh",),
    "Dadra and Nagar Haveli and Daman and Diu": (
        "dadra and nagar haveli and daman and diu", "dadra and nagar haveli", "daman and diu"),
    "Delhi": ("delhi", "nct of delhi", "national capital territory of delhi"),
    "Jammu and Kashmir": ("jammu and kashmir", "jammu & kashmir", "j&k"),
    "Ladakh": ("ladakh",),
    "Lakshadweep": ("lakshadweep",),
    "Puducherry": ("puducherry", "pondicherry"),
}

# State capitals, major urban centres and a wide set of district headquarters/tier-2 cities.
# Common older spellings/transliterations are included as aliases.
INDIAN_CITIES = frozenset("""
Agartala Agra Ahmedabad Ahmednagar Aizawl Ajmer Akola Alappuzha Aligarh Alipurduar
Allahabad Amalapuram Ambala Amravati Amreli Amritsar Anand Anantapur Anantnag Ankleshwar
Arrah Asansol Aurangabad Ayodhya Azamgarh Badaun Bagalkot Bahraich Balasore Ballari
Balrampur Banda Bankura Banswara Baramulla Baran Bareilly Baripada Barmer Barnala
Beawar Begusarai Belagavi Belgaum Bengaluru Berhampur Bettiah Betul Bhagalpur Bharatpur
Bhavnagar Bhilai Bhilwara Bhimavaram Bhind Bhiwandi Bhiwani Bhopal Bhubaneswar Bhuj
Bikaner Bilaspur Bokaro Brahmapur Budaun Bulandshahr Burhanpur Buxar Chamarajanagar
Chamba Chandausi Chandigarh Chandrapur Changanassery Chapra Charkhi Dadri Chhatarpur
Chhindwara Chikkaballapur Chikkamagaluru Chitradurga Chittoor Churu Coimbatore Cooch Behar
Cuddalore Cuttack Dahod Daltonganj Daman Darbhanga Dehradun Deoghar Dewas Dhanbad Dhar
Dharamshala Dharmapuri Dhubri Dibrugarh Dimapur Dindigul Dispur Durg Durgapur Eluru Erode
Etawah Faizabad Faridabad Farrukhabad Fatehpur Firozabad Gadag Ganderbal Gandhinagar
Ganganagar Gaya Ghaziabad Ghazipur Giridih Godhra Gonda Gondia Gorakhpur Greater Noida
Gulbarga Guna Guntur Gurugram Gurgaon Guwahati Gwalior Hajipur Haldwani Hamirpur Hanumangarh
Hapur Hassan Hazaribagh Himatnagar Hisar Hoshangabad Hospet Hubballi Hubli Hyderabad Imphal
Indore Itanagar Jabalpur Jagdalpur Jaipur Jaisalmer Jalandhar Jalgaon Jalna Jammu Jamnagar
Jamshedpur Jaunpur Jhansi Jind Jodhpur Jorhat Junagadh Kakinada Kalaburagi Kalyan Kanchipuram
Kancheepuram Kannur Kanpur Kanyakumari Karimnagar Karnal Karur Kasaragod Kashipur Katihar
Kavaratti Kendrapara Khammam Khandwa Khargone Kochi Kohima Kolhapur Kolkata Kollam Korba Kota
Kottayam Kozhikode Kullu Kurnool Kurukshetra Latur Leh Lucknow Ludhiana Machilipatnam Madurai
Mahbubnagar Malappuram Malegaon Mandi Mangalore Mangaluru Manjeri Mathura Mau Medinipur Meerut
Mehsana Mirzapur Moga Moradabad Morena Motihari Mumbai Munger Muzaffarnagar Muzaffarpur Mysore
Mysuru Nadiad Nagaon Nagapattinam Nagpur Nanded Nandurbar Nandyal Narsinghpur Nashik Navi Mumbai
Navsari Neemuch Nellore New Delhi Nizamabad Noida Ongole Ooty Orai Osmanabad Palakkad Palamu
Palanpur Pali Panaji Panipat Panchkula Panvel Parbhani Pathanamthitta Patiala Patna Pilibhit
Pithoragarh Pondicherry Porbandar Prayagraj Pudukottai Pune Puri Purnia Raichur Raigad Raipur
Rajahmundry Rajkot Rajnandgaon Rameswaram Rampur Ranchi Ratlam Ratnagiri Rewa Rishikesh Rohtak
Rourkela Rudrapur Sagar Saharanpur Salem Samastipur Sambalpur Sangli Sangrur Saran Satara Satna
Shillong Shimla Shivamogga Sholapur Silchar Siliguri Sikar Sirsa Sitamarhi Sivakasi Siwan Solan
Solapur Sonipat Srikakulam Srinagar Sultanpur Surat Surendranagar Tadepalligudem Tamluk Thane
Thanjavur Thiruvananthapuram Thrissur Tinsukia Tiruchirappalli Tirunelveli Tirupati Tiruppur
Tumakuru Tumkur Udaipur Udupi Ujjain Ulhasnagar Una Unnao Vadodara Valsad Varanasi Vellore
Vijayawada Viluppuram Virudhunagar Visakhapatnam Vizianagaram Warangal Wardha Washim Wayanad
Yamunanagar Yavatmal
""".split())

_CITY_ALIASES = {
    "Bangalore": "Bengaluru", "Bombay": "Mumbai", "Calcutta": "Kolkata", "Madras": "Chennai",
    "Mysore": "Mysuru", "Mangalore": "Mangaluru", "Belgaum": "Belagavi",
    "Gulbarga": "Kalaburagi", "Allahabad": "Prayagraj", "Gurgaon": "Gurugram",
    "Faizabad": "Ayodhya", "Hoshangabad": "Narmadapuram", "Pondicherry": "Puducherry",
}
_CITIES = INDIAN_CITIES | frozenset(_CITY_ALIASES)


def _pattern(words):
    alternatives = sorted(set(words), key=lambda x: (-len(x), x))
    return re.compile(r"(?<![A-Za-z])(?:" + "|".join(re.escape(x) for x in alternatives) + r")(?![A-Za-z])", re.I)


_STATE_CANON = {alias.casefold(): canonical for canonical, aliases in STATE_ALIASES.items() for alias in aliases}
_CITY_CANON = {name.casefold(): _CITY_ALIASES.get(name, name) for name in _CITIES}
_STATE_RX = _pattern(_STATE_CANON)
_CITY_RX = _pattern(_CITY_CANON)
_CONTEXT_PATTERNS = (
    re.compile(r"(?i)\b(?:i|we|he|she|they|customer|applicant|claimant|borrower|policyholder)\s+"
               r"(?:(?:currently|permanently|originally)\s+)?(?:live|lives|living|reside|resides|resided|residing|"
               r"stay|stays|staying|am|are|belong|belongs)\s+(?:in|at|from|to)\s+"
               r"(?P<places>[A-Za-z][A-Za-z .,'&-]{0,100})"),
    re.compile(r"(?i)\b(?:my|our|mera|meri|hamara|humara)\s+(?:home\s*town|hometown|native\s+(?:city|place)|"
               r"home\s+city)\s+(?:is|hai)?\s*(?P<places>[A-Za-z][A-Za-z .,'&-]{0,80})"),
    re.compile(r"(?i)\b(?:city|town|village|location|district|state)\s*[:=]\s*"
               r"(?P<places>[A-Za-z][A-Za-z .,'&-]{0,80})"),
    re.compile(r"(?i)\b(?:mai|main|hum|mera|meri|hamara|humara)\b[^\n.!?;]{0,24}?"
               r"(?P<places>[A-Za-z][A-Za-z .,'&-]{0,70}?)\s+(?:mein|me|main|se)\s+"
               r"(?:hu|hoon|hun|hai|hain|rehta|rehti|rehte|rahta|rahti|rahte)\b"),
)
_PLACE_END = re.compile(r"(?i)\b(?:and|but|because|where|hai|hain|hu|hoon|hun|rehta|rehti|rehte|rahta|rahti|rahte)\b")


def known_place_spans(text: str, start: int, end: int) -> List[Span]:
    """Match gazetteer city/state names inside a context-bounded place phrase."""
    region = text[start:end]
    known = list(_CITY_RX.finditer(region)) + list(_STATE_RX.finditer(region))
    for stop in _PLACE_END.finditer(region):
        if stop.group().casefold() == "and" and any(
            match.start() < stop.start() < match.end() for match in known
        ):
            continue  # "and" is part of a gazetteer name such as Andaman and Nicobar Islands
        if any(match.end() <= stop.start() for match in known) or stop.group().casefold() != "and":
            region = region[:stop.start()]
            break
    out = []
    for match in _CITY_RX.finditer(region):
        out.append(Span(start + match.start(), start + match.end(), "CITY", 0.87, "gazetteer"))
    for match in _STATE_RX.finditer(region):
        out.append(Span(start + match.start(), start + match.end(), "STATE", 0.9, "gazetteer"))
    # Delhi is both a familiar city name and a UT; do not output two entity types for one surface.
    return [span for span in out if not (
        span.type == "CITY" and any(s.type == "STATE" and s.start == span.start and s.end == span.end for s in out)
    )]


def find_contextual_places(text: str) -> List[Span]:
    out: List[Span] = []
    for context in _CONTEXT_PATTERNS:
        for match in context.finditer(text):
            out.extend(known_place_spans(text, match.start("places"), match.end("places")))
    unique = {(span.start, span.end, span.type): span for span in out}
    return list(unique.values())


def find_cities(text: str) -> List[Span]:
    return [span for span in find_contextual_places(text) if span.type == "CITY"]


def find_states(text: str) -> List[Span]:
    return [span for span in find_contextual_places(text) if span.type == "STATE"]


def has_city_or_state_context(text: str, start: int, end: int) -> bool:
    return bool(known_place_spans(text, max(0, start - 100), end))
