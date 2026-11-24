#!/usr/bin/env python3
"""Tuesday 24 November 2026 — one day's world news in one image.

Renders a dense classic front page (1024x1024 PNG, <1 MiB) to
/output/entry.png by default. Standard library only, no network, no
environment-driven execution, deterministic: two runs are byte-identical.

All text is drawn from a filled bitmap atlas rendered from real TTFs
(tools/atlas.png + tools/atlas.json, built at build time from the
public OFL fonts in tools/fonts). Illustrations are flat shapes drawn
in code. No photographs, no copied art.
"""
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = "/output/entry.png"

W, H = 1024, 1024
PAPER = (247, 242, 231)
INK = (26, 26, 26)
NAVY = (20, 38, 74)
RED = (176, 30, 36)
GREEN = (30, 122, 52)
ORANGE = (217, 108, 30)
YELLOW = (224, 168, 0)
GRAY = (107, 107, 107)
LINE = (201, 194, 178)
DARK = (24, 24, 24)

REGION_COLORS = {
    "EUROPE": (31, 78, 121),
    "MIDDLE EAST": (122, 59, 18),
    "AFRICA": (46, 107, 52),
    "ASIA": (138, 31, 45),
    "AMERICAS": (74, 45, 122),
    "OCEANIA": (15, 107, 107),
    "WORLD": (51, 51, 51),
}

# ---------------------------------------------------------------- PNG I/O

def _unfilter(raw, w, h, bpp, ctype):
    stride = w * bpp
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        f = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out += line
        prev = line
    return bytes(out)


def read_png(path):
    """Decode an 8-bit PNG (gray, gray+alpha, RGB, RGBA, palette) to RGBA."""
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    idat = b""
    width = height = bitdepth = ctype = None
    palette = None
    trns = None
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            width, height, bitdepth, ctype, _, _, _ = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"PLTE":
            palette = chunk
        elif typ == b"tRNS":
            trns = chunk
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    assert bitdepth == 8, "only 8-bit PNG supported"
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    px = _unfilter(raw, width, height, channels, ctype)
    out = bytearray(width * height * 4)
    for i in range(width * height):
        s = i * channels
        if ctype == 0:
            g = px[s]
            # grayscale atlas: the gray value IS the alpha
            out[i * 4:i * 4 + 4] = bytes((255, 255, 255, g))
        elif ctype == 2:
            out[i * 4:i * 4 + 4] = bytes((px[s], px[s + 1], px[s + 2], 255))
        elif ctype == 3:
            pi = px[s] * 3
            a = trns[px[s]] if trns and px[s] < len(trns) else 255
            out[i * 4:i * 4 + 4] = bytes((palette[pi], palette[pi + 1],
                                          palette[pi + 2], a))
        elif ctype == 4:
            out[i * 4:i * 4 + 4] = bytes((px[s], px[s], px[s], px[s + 1]))
        else:
            out[i * 4:i * 4 + 4] = px[s:s + 4]
    return width, height, bytes(out)


def _chunk(typ, payload):
    c = struct.pack(">I", len(payload)) + typ + payload
    return c + struct.pack(">I", zlib.crc32(typ + payload) & 0xFFFFFFFF)


def write_png(path, w, h, rgb):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    data = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# ---------------------------------------------------------------- Atlas text

class Atlas:
    def __init__(self, png_path, json_path):
        self.aw, self.ah, self.pixels = read_png(png_path)
        with open(json_path, encoding="utf-8") as f:
            self.meta = json.load(f)["glyphs"]

    def width(self, role, text):
        total = 0
        glyphs = self.meta[role]
        for ch in text:
            g = glyphs.get(ch)
            if g is None:
                g = glyphs.get("?", glyphs[" "])
            total += g["adv"]
        return total

    def draw(self, cv, x, y_asc, role, text, color):
        """Draw text; y_asc is the ascender line (top of cap height zone)."""
        glyphs = self.meta[role]
        cx = x
        for ch in text:
            g = glyphs.get(ch)
            if g is None:
                g = glyphs.get("?", glyphs[" "])
            if g["w"] and g["h"]:
                cv.blit_alpha(self.pixels, self.aw,
                              g["x"], g["y"], g["w"], g["h"],
                              cx + g["dx"], y_asc + g["dy"], color)
            cx += g["adv"]
        return cx


def wrap(atlas, role, text, maxw):
    words = text.split(" ")
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if atlas.width(role, trial) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- Canvas

class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        self.clip = None
        self.fill(bg)

    def fill(self, color):
        r, g, b = color
        for i in range(0, len(self.px), 3):
            self.px[i], self.px[i + 1], self.px[i + 2] = r, g, b

    def set(self, x, y, color):
        if self.clip is not None:
            cx0, cy0, cx1, cy1 = self.clip
            if not (cx0 <= x < cx1 and cy0 <= y < cy1):
                return
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = color

    def rect(self, x, y, w, h, color):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if self.clip is not None:
            cx0, cy0, cx1, cy1 = self.clip
            x0, y0 = max(x0, cx0), max(y0, cy0)
            x1, y1 = min(x1, cx1), min(y1, cy1)
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = color

    def hline(self, x, y, w, color, t=1):
        self.rect(x, y, w, t, color)

    def vline(self, x, y, h, color, t=1):
        self.rect(x, y, t, h, color)

    def circle(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self.rect(cx - dx, cy + dy, dx * 2 + 1, 1, color)

    def ring(self, cx, cy, r, color, t=2):
        for k in range(t):
            rr = r - k
            for dy in range(-rr, rr + 1):
                dx = int((rr * rr - dy * dy) ** 0.5)
                self.set(cx - dx, cy + dy, color)
                self.set(cx + dx, cy + dy, color)

    def poly(self, pts, color):
        # scanline fill, integer coords
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(min(ys), max(ys) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    t = (y - y1) / (y2 - y1)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.rect(int(xs[k]), y, max(1, int(xs[k + 1]) - int(xs[k])), 1, color)

    def line(self, x0, y0, x1, y1, color, t=1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            self.rect(x, y, t, t, color)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def blit_scaled(self, src, dx, dy, dw, dh):
        """Nearest-neighbour downscale of another canvas into this one."""
        for yy in range(dh):
            sy = yy * src.h // dh
            for xx in range(dw):
                sx = xx * src.w // dw
                i = ((dy + yy) * self.w + (dx + xx)) * 3
                j = (sy * src.w + sx) * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = (
                    src.px[j], src.px[j + 1], src.px[j + 2])

    def blit_alpha(self, src, sw, sx, sy, w, h, dx, dy, color):
        r, g, b = color
        for yy in range(h):
            ty = dy + yy
            if ty < 0 or ty >= self.h:
                continue
            for xx in range(w):
                tx = dx + xx
                if tx < 0 or tx >= self.w:
                    continue
                a = src[((sy + yy) * sw + (sx + xx)) * 4 + 3]
                if a == 0:
                    continue
                i = (ty * self.w + tx) * 3
                if a == 255:
                    self.px[i], self.px[i + 1], self.px[i + 2] = r, g, b
                else:
                    self.px[i] = (r * a + self.px[i] * (255 - a)) // 255
                    self.px[i + 1] = (g * a + self.px[i + 1] * (255 - a)) // 255
                    self.px[i + 2] = (b * a + self.px[i + 2] * (255 - a)) // 255

# ---------------------------------------------------------------- Data
# Every story was checked against live reporting on 24 Nov 2026; see
# STORIES.md for sources. Headlines and decks are in our own words.

CARDS = [
    dict(n=1, region="WORLD", beat="TECH", place="NEW YORK",
         headline="Nvidia soars as Huang returns",
         deck="On his first day back on Tuesday, Huang returned to "
               "headquarters as shares held Monday's 31% gain and the "
               "rally spread across Asia.",
         attr="Reuters \u00b7 CNN", status="REPORTED", scene="nvidia"),
    dict(n=2, region="ASIA", beat="SECURITY", place="ULLEUNGDO, SOUTH KOREA",
         headline="Russian jets trigger Korea alert",
         deck="Russian jets entered the air defence zone near Ulleung "
               "Island, and the shelter warning lasted five minutes "
               "with no airspace violation.",
         attr="Yonhap \u00b7 Korea JoongAng Daily", status="REPORTED", scene="jets"),
    dict(n=3, region="ASIA", beat="TRADE", place="TOKYO",
         headline="Trump unveils Japan trade deal",
         deck="Washington announced a Japan deal and Indonesia terms on "
               "Tuesday, Tokyo stocks led an Asian rally, and the EU "
               "readied tariffs on $84bn of US goods.",
         attr="Reuters \u00b7 Access24", status="REPORTED", scene="trade"),
    dict(n=4, region="WORLD", beat="CLIMATE", place="ANTALYA, T\u00dcRKIYE",
         headline="After COP31, focus turns to reform",
         deck="Stiell seeks advice on fixing a process one country can "
               "block.",
         attr="BBC \u00b7 UN News", status="ONGOING", scene="cop"),
    dict(n=5, region="EUROPE", beat="WAR", place="NOVOSHAKHTINSK, RUSSIA",
         headline="Refinery fire burns after drone strike",
         deck="The refinery is still ablaze after the overnight drone "
               "strike.",
         attr="Kyiv Independent \u00b7 Liveuamap", status="ONGOING", scene="refinery"),
    dict(n=6, region="MIDDLE EAST", beat="WAR", place="KHAN YOUNIS, GAZA",
         headline="Israeli strike kills three in Gaza",
         deck="Three died near a police post in Khan Younis.",
         attr="Reuters", status="REPORTED", scene="gaza"),
    dict(n=7, region="AMERICAS", beat="TRANSPORT", place="CHICAGO, US",
         headline="O'Hare stop lifted for holiday rush",
         deck="The FAA lifted the stop ahead of the Thanksgiving travel "
               "peak.",
         attr="FAA \u00b7 AP", status="REPORTED", scene="airport"),
    dict(n=8, region="AMERICAS", beat="POLITICS", place="WASHINGTON, US",
         headline="Lawmakers protest Huang's return",
         deck="Lawmakers object as Nvidia posts its best day since "
               "2003.",
         attr="Reuters", status="REPORTED", scene="capitol"),
    dict(n=9, region="EUROPE", beat="ECONOMY", place="FRANKFURT, EU",
         headline="EU leaders set to agree ECB team this week",
         deck="Leaders are set to agree the ECB team at this week's "
               "meeting.",
         attr="FXStreet \u00b7 Reuters", status="REPORTED", scene="ecb"),
    dict(n=10, region="ASIA", beat="DISASTER", place="CIKANDE, INDONESIA",
         headline="Rescue goes on at factory fire site",
         deck="Rescuers kept searching for missing workers.",
         attr="Careerindia \u00b7 Antara", status="ONGOING", scene="factory"),
    dict(n=11, region="ASIA", beat="DISASTER", place="HIMALAYAS",
         headline="Himalayan flood: 4 dead, 100 missing",
         deck="The army searched for scores missing after the valley "
               "flood.",
         attr="Access24 \u00b7 AP", status="ONGOING", scene="flood"),
    dict(n=12, region="AFRICA", beat="WAR", place="KHARTOUM, SUDAN",
         headline="RSF drones hit Sudan power stations",
         deck="Drone strikes on power stations cut power across Sudan.",
         attr="C54 \u00b7 Reuters", status="REPORTED", scene="blackout"),
    dict(n=13, region="AFRICA", beat="POLITICS", place="PRETORIA, SOUTH AFRICA",
         headline="South Africans vote as ANC faces discontent",
         deck="Voters tested the governing party over failing services.",
         attr="C54 \u00b7 Reuters", status="REPORTED", scene="ballot"),
]

ALSO = [
    # (number, headline, one-sentence clause, source). Headline + clause
    # together read as a full summary sentence; every clause was
    # measured to fit its column at sans8 (<=196px incl. source).
    (14, "Macron: Niger coup dangerous",
     "Macron called the takeover dangerous.", "C54"),
    (15, "Fresh Russian attacks near Kyiv",
     "Russian forces struck near Kyiv again.", "Careerindia"),
    (16, "Ship fire in Gulf of Finland",
     "The crew escaped the burning ship safely.", "Careerindia"),
    (17, "EU readies $84bn tariff retaliation",
     "Brussels readied tariffs on $84bn of US goods.", "Reuters"),
    (18, "US hits 35 Iran shadow banks",
     "35 shadow banks were designated.", "US Treasury"),
    (19, "Hamas yet to answer truce offer",
     "Qatar said Hamas had not yet replied.", "Arab Press"),
    (20, "Koya families flee Israeli raids",
     "Families fled Israeli raids in southern Syria.", "Starlit Daily"),
    (21, "DRC enacts constitutional reform",
     "Tshisekedi signed the reform law into force.", "C54"),
    (22, "Kenya secures 293,600 Saudi jobs",
     "Nairobi secured 293,600 jobs in Saudi Arabia.", "C54"),
    (23, "Kenya discharges last Ebola case",
     "Kenya discharged its last Ebola patient.", "C54"),
    (24, "Drone strike kills four in Chad",
     "Four died in a strike near the Sudan border.", "C54"),
    (25, "Nigeria starts building warships",
     "Nigeria began building warships at home.", "C54"),
    (26, "Typhoid jabs for 50M children",
     "Bangladesh began vaccinating 50M children.", "Access24"),
    (27, "SoftBank to invest $2bn in Intel",
     "SoftBank will invest $2 billion in Intel.", "Access24"),
    (28, "India energy import bill rises",
     "India's energy import bill rose again.", "Careerindia"),
    (29, "Gukesh begins chess title defence",
     "The champion opened his first title defence.", "Careerindia"),
    (30, "74% of Latinos report ICE activity",
     "A poll found 74% saw ICE activity nearby.", "Reuters"),
    (31, "Giuliani gets Medal of Freedom",
     "Giuliani received the medal on Tuesday.", "CNN"),
    (32, "Trump to meet NATO chief Rutte",
     "Trump meets Rutte in Florida on Wednesday.", "Reuters"),
    (33, "Trump speeds up executions",
     "Trump ordered federal executions sped up.", "DPA"),
    (34, "Australia on top in Test decider",
     "Australia took charge of the Test decider.", "C54"),
    (35, "Australia fines Big Tech up to 5%",
     "Firms face fines up to 5% of global revenue.", "Reuters"),
]

NUMBERS = [
    ("+31%", "Nvidia shares, Monday close"),
    ("5 MIN", "Ulleungdo air-raid alert"),
    ("293,600", "Saudi jobs secured by Kenya"),
    ("$2BN", "SoftBank investment in Intel"),
    ("50M", "children in typhoid drive"),
    ("9,000", "Ulleungdo residents told to shelter"),
]

TIMELINE = [
    ("00:15 UTC", "Japan, Indonesia deals"),
    ("07:52 KST", "Ulleungdo alert"),
    ("MORNING", "COP reform sought"),
    ("AFTERNOON", "Sudan grid hit"),
    ("EVENING", "South Africa votes"),
]

PINS = [  # (story number, lon, lat)
    (1, -95, 38), (2, 130, 37.5), (3, 139, 35), (4, 30.7, 36.9),
    (5, 39.9, 47.7), (6, 34.45, 31.35), (7, -87.6, 41.9), (8, -77, 38.9),
    (9, 8.68, 50.11), (10, 106.3, -6.3), (11, 85, 28), (12, 32.5, 15.6),
    (13, 28.2, -25.7),
]

DATE_CHECK_LEFT_OUT = (
    "COP31 collapse, 22 Nov \u00b7 Hong Kong turnout 98.79%, 22 Nov \u00b7 "
    "Liverpool 4\u20130 Man Utd, 22 Nov \u00b7 Verstappen Las Vegas GP, 22 Nov \u00b7 "
    "Alcaraz ATP Finals, 22\u201323 Nov \u00b7 India 720/9 Test draw, 23 Nov \u00b7 "
    "ICE Seattle arrests, 21 Nov \u00b7 Russian toll study, 23 Nov \u00b7 "
    "Libya ship strikes, 23 Nov \u00b7 Brazil storm, 20 Nov \u00b7 Iran blockade "
    "warning, 23 Nov \u00b7 Poland missiles, 20 Nov \u00b7 ICJ Rohingya ruling, "
    "19 Nov \u00b7 Huang resigns, 12 Nov"
)

# ---------------------------------------------------------------- Map

CONTINENTS = [
    [(-168, 66), (-140, 70), (-125, 71), (-110, 68), (-95, 69), (-85, 66),
     (-80, 62), (-75, 58), (-65, 60), (-55, 52), (-60, 47), (-70, 42),
     (-75, 35), (-80, 32), (-81, 26), (-84, 30), (-90, 29), (-97, 26),
     (-97, 16), (-92, 15), (-86, 12), (-83, 9), (-79, 9), (-85, 14),
     (-92, 14), (-97, 16), (-105, 20), (-110, 23), (-114, 28), (-120, 34),
     (-124, 40), (-124, 48), (-130, 55), (-140, 60), (-155, 58), (-165, 60)],
    [(-58, 64), (-52, 60), (-45, 60), (-40, 65), (-30, 68), (-22, 70),
     (-25, 76), (-35, 78), (-55, 76), (-60, 70)],
    [(-79, 9), (-72, 11), (-62, 10), (-52, 5), (-50, 0), (-44, -3),
     (-35, -8), (-38, -15), (-40, -22), (-48, -28), (-52, -33), (-58, -38),
     (-62, -41), (-65, -45), (-68, -50), (-70, -54), (-73, -50), (-73, -40),
     (-72, -30), (-70, -20), (-77, -12), (-81, -5), (-80, 0)],
    [(-10, 37), (-9, 43), (-2, 49), (0, 51), (5, 53), (8, 57), (10, 59),
     (18, 56), (21, 55), (24, 59), (30, 60), (28, 62), (30, 66), (28, 70),
     (20, 70), (15, 68), (12, 64), (8, 58), (5, 58), (2, 55), (0, 52),
     (-2, 50), (-5, 48), (-8, 43)],
    [(-5, 50), (-3, 53), (-5, 56), (-2, 58), (0, 53), (-1, 51)],
    [(-17, 15), (-16, 20), (-10, 27), (-5, 35), (0, 36), (10, 37),
     (11, 34), (15, 32), (20, 32), (25, 32), (30, 31), (32, 31), (35, 28),
     (37, 22), (39, 18), (41, 12), (43, 11), (48, 11), (51, 12), (48, 5),
     (42, 0), (40, -5), (40, -12), (36, -18), (33, -26), (28, -33),
     (20, -35), (17, -32), (15, -27), (12, -18), (12, -10), (9, -1),
     (9, 4), (-8, 5), (-13, 8)],
    [(30, 62), (40, 68), (50, 69), (60, 69), (70, 72), (80, 73), (90, 75),
     (100, 77), (110, 74), (120, 73), (130, 72), (140, 72), (150, 70),
     (158, 66), (162, 60), (158, 56), (155, 52), (150, 48), (145, 45),
     (140, 42), (135, 38), (130, 35), (127, 33), (122, 30), (120, 25),
     (115, 22), (110, 20), (108, 15), (105, 10), (103, 7), (100, 8),
     (98, 12), (95, 16), (92, 20), (88, 22), (85, 19), (80, 15), (77, 8),
     (75, 10), (72, 15), (68, 20), (66, 24), (62, 25), (58, 26), (55, 26),
     (52, 28), (50, 29), (48, 30), (44, 29), (42, 25), (40, 22), (38, 20),
     (35, 28), (35, 36), (30, 36), (27, 37), (23, 36), (22, 40), (26, 42),
     (28, 45), (30, 48), (32, 52), (35, 55), (33, 60)],
    [(95, 5), (98, 8), (100, 5), (103, 2), (105, 0), (108, -3), (110, -6),
     (114, -8), (118, -9), (122, -10), (125, -9), (128, -6), (130, -3),
     (128, 0), (125, 2), (120, 0), (115, 2), (110, 0), (105, 2)],
    [(130, 31), (133, 34), (136, 35), (139, 36), (141, 39), (141, 42),
     (143, 44), (145, 44), (143, 40), (140, 37), (137, 35), (133, 33)],
    [(113, -22), (114, -30), (115, -34), (118, -35), (124, -33), (129, -32),
     (132, -32), (135, -35), (138, -35), (140, -38), (145, -38), (150, -37),
     (153, -32), (153, -27), (150, -22), (146, -19), (142, -15), (142, -11),
     (137, -12), (135, -15), (132, -12), (130, -13), (126, -14), (122, -17),
     (118, -20)],
    [(167, -45), (170, -42), (173, -40), (176, -38), (178, -37), (176, -40),
     (173, -42), (170, -44)],
]


def _inside(lon, lat, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x:
                inside = not inside
    return inside


def draw_map(cv, x, y, w, h):
    cv.rect(x, y, w, h, (232, 238, 240))
    cols, rows = 72, 30
    cw, ch = w / cols, h / rows
    for r in range(rows):
        lat = 78 - (r + 0.5) * (136 / rows)
        for c in range(cols):
            lon = -180 + (c + 0.5) * (360 / cols)
            if any(_inside(lon, lat, p) for p in CONTINENTS):
                cv.rect(int(x + c * cw) + 1, int(y + r * ch) + 1,
                        max(1, int(cw) - 2), max(1, int(ch) - 2), (90, 110, 130))
    for n, lon, lat in PINS:
        px = int(x + (lon + 180) / 360 * w)
        py = int(y + (78 - lat) / 136 * h)
        cv.circle(px, py, 7, RED)
        cv.ring(px, py, 7, (255, 255, 255), 1)
        cv.circle(px, py, 2, (255, 255, 255))

# ---------------------------------------------------------------- Scenes
# Flat drawn illustrations, one per card. Each draws inside (x, y, w, h).

def _sky(cv, x, y, w, h, top, bot):
    cv.rect(x, y, w, h // 2, top)
    cv.rect(x, y + h // 2, w, h - h // 2, bot)


def scene_nvidia(cv, x, y, w, h):
    cv.rect(x, y, w, h, (16, 24, 40))
    cv.rect(x, y + h - 26, w, 26, (10, 16, 28))
    bars = [14, 22, 20, 32, 42, 52]
    bw = (w - 40) // len(bars)
    for i, bh in enumerate(bars):
        bx = x + 20 + i * bw
        cv.rect(bx + 2, y + h - 26 - bh, bw - 6, bh, (34, 197, 94) if i < 5 else (118, 230, 150))
    # trend line RISES with the bars (low left, high right)
    cv.line(x + 22, y + h - 32, x + w - 22, y + 14, (250, 204, 21), 2)
    cv.circle(x + w - 22, y + 14, 5, (250, 204, 21))
    cv.circle(x + 22, y + h - 32, 4, (250, 204, 21))
    # chip
    cv.rect(x + 16, y + 12, 34, 34, (34, 197, 94))
    cv.rect(x + 24, y + 20, 18, 18, (16, 24, 40))
    cv.rect(x + 28, y + 24, 10, 10, (118, 230, 150))


def _jet(cv, nx, ny, s, body=(232, 232, 232), dark=(70, 80, 95)):
    """A jet aircraft in right-facing profile. (nx, ny) = nose tip,
    s = length in px. Pointed nose, fuselage, cockpit, swept wing,
    tail fin, tailplane and a short contrail."""
    L = float(s)

    def P(fx, fy):
        return (int(nx + fx * L), int(ny + fy * L))

    # fuselage: pointed nose, straight body, flat tail
    cv.poly([P(0, 0.02), P(-0.55, -0.02), P(-0.85, 0.0), P(-0.85, 0.10),
             P(-0.55, 0.12), P(0, 0.08)], body)
    # cockpit windows near the nose
    cv.poly([P(-0.18, 0.01), P(-0.08, 0.015), P(-0.08, 0.05),
             P(-0.18, 0.05)], (30, 60, 110))
    # tail fin (vertical stabiliser) rising from the rear top
    cv.poly([P(-0.62, 0.0), P(-0.78, -0.30), P(-0.70, -0.30),
             P(-0.55, 0.0)], dark)
    # swept main wing below the fuselage
    cv.poly([P(-0.30, 0.10), P(-0.52, 0.42), P(-0.38, 0.42),
             P(-0.18, 0.10)], body)
    # tailplane
    cv.poly([P(-0.68, 0.08), P(-0.82, 0.24), P(-0.74, 0.24),
             P(-0.60, 0.08)], body)
    # engine exhaust + short contrail behind the tail
    cv.rect(int(nx - 0.98 * L), int(ny + 0.03 * L), int(0.13 * L), 3,
            (255, 255, 255))


def scene_jets(cv, x, y, w, h):
    _sky(cv, x, y, w, h, (58, 110, 165), (120, 165, 205))
    cv.circle(x + w - 30, y + 22, 16, (245, 222, 160))
    cv.poly([(x + 8, y + h - 8), (x + w // 2 - 10, y + h - 34),
             (x + w - 8, y + h - 8)], (46, 90, 60))
    cv.rect(x + w // 2 - 14, y + h - 52, 28, 20, (46, 90, 60))
    cv.circle(x + w // 2, y + h - 54, 3, RED)
    _jet(cv, x + 132, y + 28, 70)
    _jet(cv, x + 72, y + 54, 44, (205, 205, 205), (60, 68, 82))


def scene_trade(cv, x, y, w, h):
    _sky(cv, x, y, w, h, (210, 225, 235), (170, 195, 210))
    cv.rect(x, y + h - 30, w, 30, (38, 84, 124))
    cv.poly([(x + 10, y + h - 30), (x + w - 10, y + h - 30),
             (x + w - 30, y + h - 12), (x + 30, y + h - 12)], (24, 48, 74))
    cols = [(176, 30, 36), (224, 168, 0), (34, 120, 90), (31, 78, 121)]
    for i, c in enumerate(cols):
        cv.rect(x + 24 + i * 62, y + h - 78, 54, 22, c)
        cv.rect(x + 24 + i * 62, y + h - 102, 54, 22, cols[(i + 2) % 4])
    cv.rect(x + w - 46, y + 12, 30, 34, (176, 30, 36))
    cv.circle(x + w - 31, y + 29, 9, (255, 255, 255))


def scene_cop(cv, x, y, w, h):
    cv.rect(x, y, w, h, (214, 228, 216))
    cv.circle(x + w // 2, y + h // 2 + 2, 34, (52, 130, 90))
    cv.poly([(x + w // 2 - 30, y + h // 2 - 18), (x + w // 2 - 8, y + h // 2 - 26),
             (x + w // 2 - 2, y + h // 2 - 6), (x + w // 2 - 26, y + h // 2 + 2)],
            (120, 190, 120))
    cv.poly([(x + w // 2 + 6, y + h // 2 - 22), (x + w // 2 + 30, y + h // 2 - 14),
             (x + w // 2 + 18, y + h // 2 + 10), (x + w // 2 - 2, y + h // 2 + 2)],
            (120, 190, 120))
    cv.poly([(x + w // 2 - 12, y + h // 2 + 14), (x + w // 2 + 12, y + h // 2 + 18),
             (x + w // 2 + 4, y + h // 2 + 30), (x + w // 2 - 18, y + h // 2 + 26)],
            (120, 190, 120))
    cv.line(x + w // 2 - 40, y + h // 2 - 40, x + w // 2 + 40, y + h // 2 + 40, RED, 5)
    cv.rect(x + 10, y + h - 22, 46, 14, (176, 30, 36))
    cv.rect(x + w - 56, y + h - 22, 46, 14, (31, 78, 121))


def scene_refinery(cv, x, y, w, h):
    cv.rect(x, y, w, h, (32, 28, 34))
    for i in range(5):
        cv.circle(x + 20 + i * 55, y + 16, 12, (70, 66, 74))
    cv.rect(x + 16, y + h - 46, 14, 46, (90, 88, 96))
    cv.rect(x + 44, y + h - 62, 18, 62, (90, 88, 96))
    cv.rect(x + 78, y + h - 38, 26, 38, (120, 118, 126))
    cv.rect(x + 120, y + h - 54, 16, 54, (90, 88, 96))
    cv.rect(x + 150, y + h - 40, 30, 40, (120, 118, 126))
    cv.rect(x + 200, y + h - 58, 14, 58, (90, 88, 96))
    for fx, fh in [(x + 52, 34), (x + 128, 44), (x + 210, 30), (x + 162, 26)]:
        cv.poly([(fx - 12, y + h - 40), (fx, y + h - 40 - fh),
                 (fx + 12, y + h - 40)], (240, 120, 20))
        cv.poly([(fx - 6, y + h - 40), (fx, y + h - 40 - fh + 14),
                 (fx + 6, y + h - 40)], (250, 200, 40))
    cv.rect(x, y + h - 8, w, 8, (60, 56, 62))


def scene_gaza(cv, x, y, w, h):
    _sky(cv, x, y, w, h, (196, 160, 120), (150, 130, 110))
    # flat-roofed skyline
    for bx, bw, bh in [(8, 34, 34), (48, 26, 46), (80, 40, 30), (126, 30, 52),
                       (162, 36, 38), (204, 28, 48), (238, 40, 32)]:
        cv.rect(x + bx, y + h - bh, bw, bh, (70, 66, 72))
        cv.rect(x + bx, y + h - bh, bw, 3, (52, 48, 52))
    # smoke column rising over one roof
    for sx, sy, sr in [(x + 140, y + h - 66, 9), (x + 146, y + h - 78, 11),
                       (x + 138, y + h - 90, 8)]:
        cv.circle(sx, sy, sr, (120, 116, 118))
    # small drone in the sky
    dx, dy = x + w - 70, y + 16
    cv.rect(dx - 8, dy, 16, 4, (40, 40, 40))
    cv.rect(dx - 2, dy + 4, 4, 6, (40, 40, 40))
    cv.rect(dx - 16, dy - 2, 10, 2, (40, 40, 40))
    cv.rect(dx + 6, dy - 2, 10, 2, (40, 40, 40))
    cv.rect(x, y + h - 6, w, 6, (52, 48, 52))


def scene_airport(cv, x, y, w, h):
    _sky(cv, x, y, w, h, (150, 185, 215), (200, 215, 230))
    cv.rect(x, y + h - 26, w, 26, (90, 95, 100))
    cv.rect(x, y + h - 20, w, 3, (255, 255, 255))
    cv.rect(x + w - 40, y + 10, 12, h - 36, (120, 120, 120))
    cv.rect(x + w - 46, y + 6, 24, 10, (90, 90, 90))
    px, py = x + 30, y + h // 2
    cv.poly([(px, py), (px + 120, py - 6), (px + 150, py + 2), (px + 120, py + 10),
             (px + 30, py + 12), (px + 10, py + 22), (px + 2, py + 10)], (240, 240, 240))
    cv.poly([(px + 40, py - 6), (px + 52, py - 26), (px + 62, py - 6)], (240, 240, 240))
    cv.rect(px + 96, py - 2, 34, 6, (31, 78, 121))


def scene_capitol(cv, x, y, w, h):
    cv.rect(x, y, w, h, (228, 222, 205))
    cx, cy = x + w // 2, y + h - 30
    cv.poly([(cx - 70, cy), (cx + 70, cy), (cx + 46, cy - 26), (cx - 46, cy - 26)],
            (240, 236, 220))
    cv.circle(cx, cy - 26, 26, (240, 236, 220))
    cv.rect(cx - 3, cy - 60, 6, 10, (240, 236, 220))
    for i in range(5):
        cv.rect(cx - 58 + i * 24, cy - 22, 8, 22, (200, 192, 170))
    cv.rect(x + w - 44, y + 10, 30, 40, RED)
    cv.rect(x + w - 44, y + 10, 30, 6, (255, 255, 255))
    cv.rect(x + w - 44, y + 44, 30, 6, (255, 255, 255))


def scene_ecb(cv, x, y, w, h):
    cv.rect(x, y, w, h, (222, 228, 232))
    # bank facade, large and centred: pediment + thick columns + steps
    cx = x + w // 2 - 18
    cv.poly([(cx - 72, y + 34), (cx + 72, y + 34), (cx, y + 6)], (31, 78, 121))
    cv.circle(cx, y + 22, 9, (255, 255, 255))
    cv.rect(cx - 72, y + 34, 144, 6, (31, 78, 121))
    for i in range(4):
        cv.rect(cx - 62 + i * 34, y + 40, 13, 32, (245, 245, 245))
        cv.rect(cx - 62 + i * 34, y + 40, 13, 4, (200, 200, 200))
    cv.rect(cx - 72, y + 72, 144, 5, (31, 78, 121))
    cv.rect(x + 8, y + h - 12, w - 16, 5, (180, 184, 188))
    cv.rect(x + 16, y + h - 7, w - 32, 4, (160, 164, 168))
    # big gold coin stack, right side
    for i in range(3):
        cv.rect(x + w - 56, y + h - 26 - i * 8, 34, 6, (224, 168, 0))
    cv.circle(x + w - 39, y + h - 52, 13, (224, 168, 0))
    cv.ring(x + w - 39, y + h - 52, 13, (176, 130, 0), 2)
    cv.circle(x + w - 39, y + h - 52, 5, (176, 130, 0))
    # EU flag, top left, larger with a ring of stars
    cv.rect(x + 10, y + 10, 30, 19, (0, 51, 153))
    for dx, dy in [(6, 0), (5, 4), (0, 6), (-5, 4),
                   (-6, 0), (-5, -4), (0, -6), (5, -4)]:
        cv.rect(x + 25 + dx - 1, y + 19 + dy - 1, 3, 3, (255, 204, 0))


def scene_factory(cv, x, y, w, h):
    _sky(cv, x, y, w, h, (190, 190, 185), (150, 150, 145))
    # tall chimneys with smoke puffs, left
    cv.rect(x + 138, y + 8, 14, 62, (100, 98, 94))
    cv.rect(x + 138, y + 8, 14, 5, (70, 68, 66))
    cv.rect(x + 158, y + 18, 14, 52, (100, 98, 94))
    cv.rect(x + 158, y + 18, 14, 5, (70, 68, 66))
    for sx, sy, sr in [(x + 145, y + 2, 10), (x + 138, y + 6, 8),
                       (x + 165, y + 6, 9), (x + 172, y + 2, 7)]:
        cv.circle(sx, sy, sr, (110, 110, 108))
    # factory block with a big sawtooth roof
    cv.rect(x + 12, y + h - 46, 118, 46, (120, 118, 112))
    for i in range(4):
        cv.poly([(x + 12 + i * 30, y + h - 46), (x + 27 + i * 30, y + h - 64),
                 (x + 42 + i * 30, y + h - 46)], (90, 88, 84))
    for wx in (x + 24, x + 54, x + 84):
        cv.rect(wx, y + h - 36, 14, 12, (240, 200, 60))
    # large flames over the roof
    for fx, fh in [(x + 52, 40), (x + 96, 48)]:
        cv.poly([(fx - 14, y + h - 46), (fx, y + h - 46 - fh),
                 (fx + 14, y + h - 46)], (240, 120, 20))
        cv.poly([(fx - 7, y + h - 46), (fx, y + h - 46 - fh + 16),
                 (fx + 7, y + h - 46)], (250, 200, 40))
    # blue water jet from the right, arcing onto the flames
    cv.line(x + w - 8, y + h - 6, x + w - 52, y + h - 58, (30, 110, 200), 4)
    cv.circle(x + w - 54, y + h - 60, 4, (30, 110, 200))
    cv.circle(x + w - 62, y + h - 52, 3, (90, 160, 230))


def scene_flood(cv, x, y, w, h):
    _sky(cv, x, y, w, h, (140, 170, 200), (180, 200, 220))
    # two steep mountains with big snowcaps
    cv.poly([(x, y + h - 36), (x + 62, y + 6), (x + 124, y + h - 36)], (110, 130, 150))
    cv.poly([(x + 46, y + 6), (x + 62, y - 4), (x + 78, y + 6)], (255, 255, 255))
    cv.poly([(x + 52, y + 16), (x + 62, y + 6), (x + 72, y + 16)], (235, 240, 245))
    cv.poly([(x + 96, y + h - 36), (x + 172, y + 2), (x + 248, y + h - 36)], (90, 112, 135))
    cv.poly([(x + 158, y + 2), (x + 172, y - 6), (x + 186, y + 2)], (255, 255, 255))
    cv.poly([(x + 162, y + 12), (x + 172, y + 2), (x + 182, y + 12)], (235, 240, 245))
    # wide muddy flood water with white crests, bottom third
    cv.poly([(x, y + h - 40), (x + 60, y + h - 52), (x + 120, y + h - 36),
             (x + 180, y + h - 54), (x + w, y + h - 36), (x + w, y + h),
             (x, y + h)], (122, 92, 60))
    cv.line(x + 6, y + h - 30, x + 90, y + h - 38, (240, 235, 220), 2)
    cv.line(x + 110, y + h - 22, x + 190, y + h - 30, (240, 235, 220), 2)
    cv.line(x + 30, y + h - 12, x + 130, y + h - 18, (200, 190, 170), 2)
    # house half-submerged in the water, roof above the surface
    cv.rect(x + w - 78, y + h - 58, 40, 30, (200, 120, 70))
    cv.poly([(x + w - 84, y + h - 58), (x + w - 58, y + h - 76),
             (x + w - 32, y + h - 58)], (140, 50, 40))
    cv.rect(x + w - 64, y + h - 46, 10, 12, (60, 40, 30))


def scene_blackout(cv, x, y, w, h):
    cv.rect(x, y, w, h, (18, 20, 30))
    # dark skyline: most windows dead, a few lit yellow
    for bx in (x + 12, x + 52, x + 92, x + 132, x + 172, x + 212):
        bh = 44 if bx % 80 else 58
        cv.rect(bx, y + h - bh, 30, bh, (40, 44, 58))
        cv.rect(bx + 6, y + h - bh + 8, 5, 5, (250, 204, 21))
        cv.rect(bx + 18, y + h - 20, 5, 5, (60, 60, 70))
        cv.rect(bx + 6, y + h - 32, 5, 5, (60, 60, 70))
    # big lightning bolt over the city
    cv.poly([(x + 58, y + 4), (x + 40, y + 38), (x + 56, y + 38),
             (x + 38, y + 72), (x + 76, y + 28), (x + 58, y + 28),
             (x + 76, y + 4)], (250, 204, 21))
    # transmission pylon with cross-arms and sagging lines
    cv.rect(x + 196, y + 8, 6, 56, (120, 120, 130))
    cv.rect(x + 182, y + 12, 34, 5, (120, 120, 130))
    cv.rect(x + 186, y + 26, 26, 5, (120, 120, 130))
    cv.line(x + 182, y + 14, x + 150, y + 30, (120, 120, 130), 2)
    cv.line(x + 216, y + 14, x + 248, y + 30, (120, 120, 130), 2)
    cv.rect(x, y + h - 6, w, 6, (10, 12, 18))


def scene_ballot(cv, x, y, w, h):
    cv.rect(x, y, w, h, (240, 235, 215))
    # South Africa flag stripes across the top
    cv.rect(x, y, w, 9, (0, 122, 70))
    cv.rect(x, y + 9, w, 5, (255, 255, 255))
    cv.rect(x, y + 14, w, 9, (200, 40, 40))
    cv.rect(x, y + 23, w, 5, (255, 255, 255))
    cv.rect(x, y + 28, w, 9, (0, 40, 120))
    # large ballot box with a white check
    cx = x + w // 2
    cv.rect(cx - 58, y + h - 52, 116, 52, (31, 78, 121))
    cv.rect(cx - 58, y + h - 52, 116, 10, (20, 50, 90))
    cv.rect(cx - 58, y + h - 52, 116, 3, (255, 255, 255))
    cv.poly([(cx - 38, y + h - 28), (cx - 24, y + h - 10),
             (cx + 16, y + h - 42)], (255, 255, 255))
    # ballot slip dropping into the slot
    cv.rect(cx - 18, y + h - 68, 36, 18, (255, 255, 255))
    cv.rect(cx - 18, y + h - 68, 36, 4, (31, 78, 121))
    cv.line(cx - 12, y + h - 58, cx + 12, y + h - 58, (180, 180, 180), 1)


SCENES = {
    "nvidia": scene_nvidia, "jets": scene_jets, "trade": scene_trade,
    "cop": scene_cop, "refinery": scene_refinery, "gaza": scene_gaza,
    "airport": scene_airport, "capitol": scene_capitol, "ecb": scene_ecb,
    "factory": scene_factory, "flood": scene_flood, "blackout": scene_blackout,
    "ballot": scene_ballot,
}

STATUS_COLORS = {"REPORTED": GREEN, "CLAIM": YELLOW, "ONGOING": ORANGE}

# ---------------------------------------------------------------- Layout

def text_center(atlas, cv, cx, y_asc, role, text, color):
    w = atlas.width(role, text)
    atlas.draw(cv, cx - w // 2, y_asc, role, text, color)


def badge(cv, at, x, y, text, role, bg, fg=(255, 255, 255)):
    w = at.width(role, text) + 10
    cv.rect(x, y, w, 14, bg)
    at.draw(cv, x + 5, y + 1, role, text, fg)
    return w


def draw_card(cv, at, card, x, y, w, h, big):
    cv.rect(x, y, w, h, (255, 255, 255))
    cv.rect(x, y, w, 1, INK)
    cv.rect(x, y + h - 1, w, 1, INK)
    cv.rect(x, y, 1, h, INK)
    cv.rect(x + w - 1, y, 1, h, INK)
    scene_h = 76 if big == 1 else (30 if big == 2 else 38)
    # scenes are drawn at a fixed 88px height, then scaled into the slot
    tmp = Canvas(w - 2, 88, (0, 0, 0))
    SCENES[card["scene"]](tmp, 0, 0, w - 2, 88)
    cv.blit_scaled(tmp, x + 1, y + 1, w - 2, scene_h)
    # number badge
    cv.circle(x + 15, y + 15, 11, NAVY)
    cv.ring(x + 15, y + 15, 11, (255, 255, 255), 1)
    num = str(card["n"])
    at.draw(cv, x + 15 - at.width("sansb11", num) // 2, y + 7, "sansb11", num,
            (255, 255, 255))
    # status badge on scene, top right
    st = card["status"]
    sw = at.width("sansb9", st) + 10
    cv.rect(x + w - sw - 5, y + 6, sw, 14, STATUS_COLORS[st])
    at.draw(cv, x + w - sw, y + 7, "sansb9", st, (255, 255, 255))
    # place chip, bottom-left of scene
    pw = at.width("sansb9", card["place"]) + 10
    cv.rect(x + 5, y + scene_h - 19, pw, 14, (0, 0, 0))
    at.draw(cv, x + 10, y + scene_h - 18, "sansb9", card["place"], (255, 255, 255))
    ty = y + scene_h + 6
    tag = card["region"] + " \u00b7 " + card["beat"]
    at.draw(cv, x + 8, ty, "sansb10", tag, REGION_COLORS[card["region"]])
    if big == 1:
        # attribution sits on the tag line for the large cards
        aw = at.width("sans9", card["attr"])
        at.draw(cv, x + w - 8 - aw, ty + 1, "sans9", card["attr"], GRAY)
    ty += 14
    hrole = "bask20" if big == 1 else ("bask17" if big == 2 else "bask15")
    lh = 22 if big == 1 else (18 if big == 2 else 17)
    lines = wrap(at, hrole, card["headline"], w - 16)
    for ln in lines[:2]:
        at.draw(cv, x + 8, ty, hrole, ln, INK)
        ty += lh
    if big == 1:
        drole, dlh, dmax = "gelasio13", 15, 3
    elif big == 2:
        drole, dlh, dmax = "gelasio12", 13, 2
    else:
        # row 3 (v3): a real 1-2 line deck, like rows 1-2
        drole, dlh, dmax = "gelasio12", 13, 2
    dlines = wrap(at, drole, card["deck"], w - 16)
    for ln in dlines[:dmax]:
        at.draw(cv, x + 8, ty, drole, ln, (60, 60, 60))
        ty += dlh
    if big in (2, 3):
        arole = "sans8"
        at.draw(cv, x + 8, y + h - 11, arole, card["attr"], GRAY)


def render():
    at = Atlas(os.path.join(HERE, "tools", "atlas.png"),
               os.path.join(HERE, "tools", "atlas.json"))
    cv = Canvas(W, H, PAPER)
    # top strip
    at.draw(cv, 14, 4, "sansb11", "THE WORLD IN ONE DAY", NAVY)
    right = "35 STORIES \u00b7 7 REGIONS \u00b7 ALL FROM THIS ONE DAY"
    at.draw(cv, W - 14 - at.width("sansb11", right), 4, "sansb11", right, INK)
    cv.hline(14, 18, W - 28, NAVY, 2)
    # masthead: date is the biggest text (Bodoni 76 fits the line)
    date = "Tuesday 24 November 2026"
    text_center(at, cv, W // 2, 20, "bodoni76", date, INK)
    # sub-headline: the three heroes
    sub = ("Nvidia soars as Huang returns \u00b7 Russian jets trigger Korea alert "
           "\u00b7 Trump unveils Japan trade deal")
    text_center(at, cv, W // 2, 130, "gelasio20", sub, RED)
    cv.hline(14, 152, W - 28, INK, 1)
    # region bar
    counts = {}
    for c in CARDS:
        counts[c["region"]] = counts.get(c["region"], 0) + 1
    for n, _head, _clause, _a in ALSO:
        pass
    also_regions = {
        14: "EUROPE", 15: "EUROPE", 16: "EUROPE", 17: "EUROPE",
        18: "MIDDLE EAST", 19: "MIDDLE EAST", 20: "MIDDLE EAST",
        21: "AFRICA", 22: "AFRICA", 23: "AFRICA", 24: "AFRICA",
        25: "AFRICA", 26: "ASIA", 27: "ASIA", 28: "ASIA", 29: "ASIA",
        30: "AMERICAS", 31: "AMERICAS", 32: "AMERICAS", 33: "AMERICAS",
        34: "OCEANIA", 35: "OCEANIA",
    }
    for n, reg in also_regions.items():
        counts[reg] = counts.get(reg, 0) + 1
    order = ["EUROPE", "MIDDLE EAST", "AFRICA", "ASIA", "AMERICAS", "OCEANIA", "WORLD"]
    cx = 14
    for reg in order:
        label = "%s %d" % (reg, counts.get(reg, 0))
        wch = at.width("sansb10", label) + 12
        cv.rect(cx, 156, wch, 18, REGION_COLORS[reg])
        at.draw(cv, cx + 6, 159, "sansb10", label, (255, 255, 255))
        cx += wch + 6
    # UTC timeline strip
    cv.rect(14, 178, W - 28, 22, NAVY)
    at.draw(cv, 20, 182, "sansb10", "THE DAY IN UTC", YELLOW)
    tx = 130
    for when, what in TIMELINE:
        seg = when + "  " + what
        at.draw(cv, tx, 183, "sans10", seg, (255, 255, 255))
        tx += at.width("sans10", seg) + 16
        if tx < W - 20:
            at.draw(cv, tx - 11, 183, "sans10", "\u2022", YELLOW)
    # numbers strip
    cv.rect(14, 204, W - 28, 44, (255, 255, 255))
    cv.rect(14, 204, W - 28, 1, INK)
    cv.rect(14, 247, W - 28, 1, INK)
    cw = (W - 28) // len(NUMBERS)
    for i, (num, label) in enumerate(NUMBERS):
        x0 = 14 + i * cw
        text_center(at, cv, x0 + cw // 2, 205, "bask30", num, NAVY)
        text_center(at, cv, x0 + cw // 2, 235, "sans9", label, GRAY)
        if i:
            cv.vline(x0, 208, 34, LINE, 1)
    # cards
    row1 = CARDS[0:3]
    xs = [14, 348, 682]
    for card, x in zip(row1, xs):
        draw_card(cv, at, card, x, 252, 326, 186, 1)
    row2 = CARDS[3:8]
    xs2 = [14, 214, 414, 614, 814]
    for card, x in zip(row2, xs2):
        draw_card(cv, at, card, x, 444, 193, 126, 2)
    row3 = CARDS[8:13]
    for card, x in zip(row3, xs2):
        draw_card(cv, at, card, x, 576, 193, 140, 3)
    # ALSO + map band (row 3 grew +44: this band starts 42px lower and
    # the map is 14px shorter; DATE CHECK + footer shift down with it)
    at.draw(cv, 14, 722, "sansb11", "ALSO ON TUESDAY 24 NOVEMBER", NAVY)
    cv.hline(14, 736, 636, INK, 1)
    at.draw(cv, 664, 722, "sansb11", "WHERE IT HAPPENED", NAVY)
    at.draw(cv, 664 + at.width("sansb11", "WHERE IT HAPPENED") + 8, 723,
            "sans9", "pins = story numbers", GRAY)
    cv.hline(664, 736, W - 28 - 650, INK, 1)
    cols = [ALSO[0:8], ALSO[8:15], ALSO[15:22]]
    colx = [14, 232, 450]
    for col, x0 in zip(cols, colx):
        yy = 744
        for n, head, clause, attr in col:
            num = str(n)
            at.draw(cv, x0, yy, "bask11", num, NAVY)
            hx = x0 + 18
            avail = 196
            htxt = head
            while at.width("bask11", htxt) > avail and " " in htxt:
                htxt = htxt.rsplit(" ", 1)[0]
            if htxt != head:
                htxt = htxt + "\u2026"
            at.draw(cv, hx, yy, "bask11", htxt, INK)
            # line 2: the full-sentence clause + source, both sans8
            cw = at.width("sans8", clause)
            at.draw(cv, hx, yy + 11, "sans8", clause, (60, 60, 60))
            at.draw(cv, hx + cw, yy + 11, "sans8", " \u00b7 " + attr, GRAY)
            yy += 21
    draw_map(cv, 664, 744, 346, 148)
    # date check
    cv.rect(14, 918, W - 28, 60, (255, 255, 255))
    cv.rect(14, 918, W - 28, 2, RED)
    cv.rect(14, 976, W - 28, 2, RED)
    cv.rect(14, 918, 2, 60, RED)
    cv.rect(W - 16, 918, 2, 60, RED)
    cv.rect(20, 924, at.width("sansb11", "DATE CHECK") + 12, 16, RED)
    at.draw(cv, 26, 927, "sansb11", "DATE CHECK", (255, 255, 255))
    lead = ("Every story on this page happened or was first reported on "
            "Tuesday 24 November 2026 (UTC). Left out because they happened "
            "on an earlier day: ")
    body = lead + DATE_CHECK_LEFT_OUT
    lines = wrap(at, "sans10", body, W - 28 - 24)
    ly = 946
    for ln in lines[:3]:
        at.draw(cv, 20, ly, "sans10", ln, INK)
        ly += 11
    # footer legend
    foot = ("HOW SURE: REPORTED = carried by the day\u2019s wires or officials \u00b7 "
            "CLAIM = one side\u2019s account, labelled as such \u00b7 ONGOING = still "
            "unfolding \u00b7 Scenes are drawn illustrations, not photographs.")
    flines = wrap(at, "roboto10", foot, W - 28)
    fy = 984
    for ln in flines:
        text_center(at, cv, W // 2, fy, "roboto10", ln, GRAY)
        fy += 11
    src = "Sources: Reuters \u00b7 BBC \u00b7 AP \u00b7 Yonhap \u00b7 Korea JoongAng Daily \u00b7 C54 \u00b7 FAA \u00b7 Careerindia \u00b7 Access24 \u00b7 FXStreet \u00b7 US Treasury"
    text_center(at, cv, W // 2, fy + 2, "roboto10", src, GRAY)
    return cv


def main(argv):
    out = argv[1] if len(argv) > 1 else OUT_DEFAULT
    cv = render()
    write_png(out, W, H, bytes(cv.px))
    print("wrote %s (%d bytes)" % (out, os.path.getsize(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
