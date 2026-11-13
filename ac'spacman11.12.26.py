#!/usr/bin/env python3
# ============================================================================
#  AC'S PAC-MAN 0.1.1a NEON EDITION  11.12.26   --  A.C Holdings / Team Flames
#  single file | pygame | HD resizable window | 60 FPS | FILES = OFF
#  Pac-Man, four classic ghosts, procedural mirrored mazes,
#  procedural arcade audio and HD neon effects (no external assets)
#  run:  pip install pygame-ce && python ac_pacman0.1.1a_neon_hd.py
# ============================================================================
import os, sys, math, random, array, time
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

W, H, FPS = 600, 400, 60
DISPLAY_W, DISPLAY_H = 1280, 720  # widescreen HD presentation; gameplay coordinates remain 600x400
T, COLS, ROWS = 16, 25, 21
OX, OY = (W - COLS * T) // 2, 32
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
HOME = (11, 9)
SPAWNS = ((11, 9), (13, 9), (11, 11), (13, 11))
PSPAWN = (11, 19)
CORNERS = ((1, 1), (23, 1), (1, 19), (23, 19))
SR = 22050
GHOST_NAMES = ("BLINKY", "PINKY", "INKY", "CLYDE")
PALETTES = [((12, 38, 210), (45, 95, 255))]
BOT_COLS = [(255, 70, 90), (255, 120, 220), (60, 230, 255), (255, 170, 50)]


# ----------------------------------------------------------------- audio ----
def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def to_sound(samples, vol=1.0):
    a = array.array("h", (int(max(-1.0, min(1.0, v * vol)) * 32000) for v in samples))
    return pygame.mixer.Sound(buffer=a.tobytes())


def synth_blip(f0, f1, dur, vol=0.35, square=False):
    n = int(SR * dur)
    out, ph = [], 0.0
    for i in range(n):
        u = i / n
        ph += (f0 + (f1 - f0) * u) / SR
        s = math.sin(2 * math.pi * ph)
        if square:
            s = 0.6 if s > 0 else -0.6
        out.append(s * (1 - u) ** 1.5 * vol)
    return out


def famicom_tone(notes, bpm=168, duty=0.25):
    """Original 2A03-inspired score: pulse lead, triangle bass, noise percussion."""
    beat = 60.0 / bpm
    step = beat / 2
    total = int(len(notes) * step * SR)
    pcm = array.array("h", [0]) * total
    for j, (lead, bass) in enumerate(notes):
        start = int(j * step * SR)
        stop = min(total, int((j + 1) * step * SR))
        lf = mtof(lead) if lead else 0
        bf = mtof(bass) if bass else 0
        for i in range(start, stop):
            t = (i - start) / SR
            u = (i - start) / max(1, stop - start)
            pulse = (1 if (t * lf) % 1 < duty else -1) * 0.27 * (1-u*.45) if lf else 0
            triangle = (4 * abs((t * bf) % 1 - .5) - 1) * .19 if bf else 0
            # Deterministic pseudo-noise percussion on each fourth step.
            noise = (((i * 1103515245 + 12345) >> 12) & 1) * .09 - .045 if j % 4 == 0 and t < .035 else 0
            pcm[i] = int(max(-1, min(1, pulse + triangle + noise)) * 22000)
    return pygame.mixer.Sound(buffer=pcm.tobytes())


# An original short 8-bit arcade tune; not a transcription of Namco music.
INTRO_NOTES = [(76,48),(79,48),(83,55),(79,55), (81,53),(84,53),(88,60),(84,60),
               (83,55),(79,55),(76,52),(79,52), (81,53),(77,53),(74,50),(72,48),
               (76,48),(79,48),(84,55),(83,55), (81,53),(77,53),(79,55),(76,55),
               (74,50),(77,50),(81,53),(77,53), (76,48),(72,48),(72,48),(None,48)]
SIREN_NOTES = [(48,36),(50,36),(52,40),(50,40),(48,36),(46,36),(45,33),(46,33)]


class Audio:
    def __init__(self):
        self.ok = False
        self.music_on = True
        self.s = {}
        try:
            pygame.mixer.pre_init(SR, -16, 1, 512)
            pygame.mixer.init()
            self.ok = True
        except Exception:
            pass

    def build(self):
        if not self.ok:
            return
        try:
            self.s["c0"] = to_sound(synth_blip(400, 620, .065, .27, True))
            self.s["c1"] = to_sound(synth_blip(620, 400, .065, .27, True))
            self.s["pow"] = to_sound(synth_blip(180, 850, .38, .30, True))
            self.s["eat"] = to_sound(synth_blip(350, 1500, .26, .32, True))
            self.s["die"] = to_sound(synth_blip(750, 55, .75, .38, True))
            self.s["nav"] = to_sound(synth_blip(600, 760, .05, .15, True))
            self.s["ok"] = to_sound(synth_blip(480, 1000, .12, .22, True))
            self.s["roll"] = famicom_tone([(72,48),(76,48),(79,55),(84,55),(79,52),(76,52),(72,48),(None,48)], bpm=135)
            self.s["win"] = to_sound(synth_blip(450, 1200, .55, .25, True))
            self.intro = famicom_tone(INTRO_NOTES)
            self.siren = famicom_tone(SIREN_NOTES, bpm=140)
            self.mch = pygame.mixer.Channel(0)
            self.mode = None
        except Exception:
            self.ok = False

    def play(self, name):
        if self.ok and name in self.s and self.music_on:
            self.s[name].play()

    def sync(self, state):
        if not self.ok:
            return
        # Menu stays silent, as in the earlier user preference.
        mode = "intro" if state == "ready" else "siren" if state == "play" else None
        if mode != self.mode:
            self.mch.stop()
            self.mode = mode
            if mode == "intro":
                self.mch.play(self.intro)
            elif mode == "siren":
                self.mch.play(self.siren, loops=-1)
        self.mch.set_volume(.24 if self.music_on else 0)

    def toggle_music(self):
        self.music_on = not self.music_on
        if self.ok:
            self.mch.set_volume(.24 if self.music_on else 0)


# ------------------------------------------------------------------ maze ----
def gen_maze(rng):
    g = [[1] * COLS for _ in range(ROWS)]

    def carve(x, y):
        g[y][x] = 0
        g[y][COLS - 1 - x] = 0

    stack, seen = [(1, 1)], {(1, 1)}
    carve(1, 1)
    while stack:
        x, y = stack[-1]
        nb = [(dx, dy) for dx, dy in DIRS
              if 1 <= x + 2 * dx <= 11 and 1 <= y + 2 * dy <= ROWS - 2 and (x + 2 * dx, y + 2 * dy) not in seen]
        if not nb:
            stack.pop()
            continue
        dx, dy = rng.choice(nb)
        carve(x + dx, y + dy)
        carve(x + 2 * dx, y + 2 * dy)
        seen.add((x + 2 * dx, y + 2 * dy))
        stack.append((x + 2 * dx, y + 2 * dy))
    for y in set(rng.sample(range(1, ROWS - 1, 2), 3)) | {9, 19}:   # centre links
        g[y][12] = 0
    for x in range(1, 12, 2):                                        # braid dead ends
        for y in range(1, ROWS - 1, 2):
            if sum(1 for dx, dy in DIRS if not g[y + dy][x + dx]) <= 1:
                cand = [(dx, dy) for dx, dy in DIRS if g[y + dy][x + dx]
                        and 1 <= x + 2 * dx <= 13 and 1 <= y + 2 * dy <= ROWS - 2]
                if cand:
                    dx, dy = rng.choice(cand)
                    carve(x + dx, y + dy)
    for _ in range(5):                                               # extra loops
        x, y = rng.randrange(1, 12, 2), rng.randrange(1, ROWS - 1, 2)
        dx, dy = rng.choice(DIRS)
        if 1 <= x + 2 * dx <= 11 and 1 <= y + 2 * dy <= ROWS - 2:
            carve(x + dx, y + dy)
    return g


def bfs(g, start):
    dist, q = {start: 0}, [start]
    for x, y in q:
        for dx, dy in DIRS:
            p = (x + dx, y + dy)
            if not g[p[1]][p[0]] and p not in dist:
                dist[p] = dist[(x, y)] + 1
                q.append(p)
    return dist


def tc(x, y):
    return OX + x * T + T // 2, OY + y * T + T // 2


def build_maze_surfs(g, pal):
    col, light = pal
    glow = pygame.Surface((W, H))
    core = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(ROWS):
        for x in range(COLS):
            if not g[y][x]:
                continue
            pygame.draw.circle(core, light, tc(x, y), 1)
            for dx, dy in ((1, 0), (0, 1)):
                X, Y = x + dx, y + dy
                if X < COLS and Y < ROWS and g[Y][X]:
                    pygame.draw.line(glow, col, tc(x, y), tc(X, Y), 7)
                    pygame.draw.line(core, light, tc(x, y), tc(X, Y), 2)
    blur = pygame.transform.smoothscale(pygame.transform.smoothscale(glow, (W // 5, H // 5)), (W, H))
    glow.fill((110, 110, 110), special_flags=pygame.BLEND_RGB_MULT)
    glow.blit(blur, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return glow, core


# -------------------------------------------------------------- graphics ----
_glow_cache = {}


def glow(surf, pos, r, col, k=1.0):
    key = (r, col, round(k, 1))
    s = _glow_cache.get(key)
    if s is None:
        s = pygame.Surface((r * 2, r * 2))
        for i in range(r, 0, -1):
            f = (1 - i / r) ** 2 * k
            pygame.draw.circle(s, tuple(min(255, int(c * f)) for c in col), (r, r), i)
        _glow_cache[key] = s
    surf.blit(s, (pos[0] - r, pos[1] - r), special_flags=pygame.BLEND_RGB_ADD)


def draw_cat(surf, x, y, d, t, r=7, col=(255, 225, 0)):
    """Classic yellow chomping disc, oriented in travel direction."""
    x, y = int(x), int(y)
    angle = math.atan2(-d[1], d[0]) if d != (0, 0) else 0.0
    opening = 0.12 + 0.43 * abs(math.sin(t * 11))
    pts = [(x, y)]
    for i in range(35):
        a = angle + opening + (2 * math.pi - 2 * opening) * i / 34
        pts.append((int(x + r * math.cos(a)), int(y - r * math.sin(a))))
    glow(surf, (x, y), max(8, r * 3), (70, 55, 0), 0.75)
    pygame.draw.polygon(surf, col, pts)
    pygame.draw.arc(surf, (255, 255, 180), (x-r+2, y-r+2, (r-2)*2, (r-2)*2), .6, 2.6, max(1, r//5))


def draw_bot(surf, x, y, col, look, t, mode):
    """Rounded ghost with scalloped skirt and directional pupils."""
    x, y = int(x), int(y)
    if mode == "eyes":
        col = None
    elif mode == "fright":
        col = (35, 50, 235)
    elif mode == "flash":
        col = (245, 245, 245)
    if col is not None:
        glow(surf, (x, y), 23, tuple(c // 3 for c in col), 0.85)
        pygame.draw.circle(surf, col, (x, y - 2), 7)
        pygame.draw.rect(surf, col, (x - 7, y - 2, 15, 8))
        pygame.draw.arc(surf, tuple(min(255, c+75) for c in col), (x-6, y-7, 12, 12), .3, 2.7, 2)
        for k in (-5, 0, 5):
            pygame.draw.circle(surf, col, (x + k, y + 6), 3)
    if mode in ("fright", "flash"):
        for ex in (-3, 3):
            pygame.draw.circle(surf, (255, 255, 255), (x + ex, y - 2), 1)
        pygame.draw.lines(surf, (255, 255, 255), False,
                          [(x - 4, y + 3), (x - 2, y + 1), (x, y + 3),
                           (x + 2, y + 1), (x + 4, y + 3)], 1)
    else:
        for ex in (-3, 3):
            pygame.draw.ellipse(surf, (255, 255, 255), (x + ex - 3, y - 5, 6, 8))
            pygame.draw.circle(surf, (30, 70, 235),
                               (x + ex + look[0], y - 1 + look[1]), 2)


# -------------------------------------------------------------- entities ----
class Mover:
    def __init__(self, tx, ty):
        self.tx, self.ty, self.d, self.t = tx, ty, (0, 0), 0.0

    def pos(self):
        return (OX + (self.tx + self.d[0] * self.t) * T + T / 2, OY + (self.ty + self.d[1] * self.t) * T + T / 2)

    def reverse(self):
        if self.d != (0, 0):
            self.tx += self.d[0]
            self.ty += self.d[1]
            self.t = 1 - self.t
            self.d = (-self.d[0], -self.d[1])


class Cat(Mover):
    def __init__(self):
        super().__init__(*PSPAWN)
        self.want, self.face = (0, 0), (1, 0)

    def step(self, g, dt, speed):
        w = self.want
        if self.d != (0, 0) and w == (-self.d[0], -self.d[1]):
            self.reverse()
        if self.d == (0, 0):
            if w != (0, 0) and not g[self.ty + w[1]][self.tx + w[0]]:
                self.d = w
            else:
                return
        self.face = self.d
        self.t += speed * dt
        while self.t >= 1:
            self.t -= 1
            self.tx += self.d[0]
            self.ty += self.d[1]
            if w != (0, 0) and not g[self.ty + w[1]][self.tx + w[0]]:
                self.d = w
            elif g[self.ty + self.d[1]][self.tx + self.d[0]]:
                self.d, self.t = (0, 0), 0.0
                break


class Bot(Mover):
    def __init__(self, kind):
        super().__init__(*SPAWNS[kind])
        self.kind, self.col = kind, BOT_COLS[kind]
        self.wait, self.fright, self.eyes = kind * 3.0 + 0.5, 0.0, False

    def choose(self, G):
        g = G.grid
        opts = [d for d in DIRS if not g[self.ty + d[1]][self.tx + d[0]]]
        if not opts:
            return (0, 0)
        if self.eyes:
            return min(opts, key=lambda d: G.home.get((self.tx + d[0], self.ty + d[1]), 999))
        rev = (-self.d[0], -self.d[1])
        nr = [d for d in opts if d != rev] or opts
        if self.fright > 0 or (self.kind == 3 and not G.scatter):
            return G.rng.choice(nr)
        c = G.cat
        if G.scatter:
            tx, ty = CORNERS[self.kind]
        elif self.kind == 1:
            tx, ty = c.tx + c.face[0] * 4, c.ty + c.face[1] * 4
        elif self.kind == 2 and abs(c.tx - self.tx) + abs(c.ty - self.ty) < 6:
            tx, ty = CORNERS[2]
        else:
            tx, ty = c.tx, c.ty
        return min(nr, key=lambda d: (self.tx + d[0] - tx) ** 2 + (self.ty + d[1] - ty) ** 2)

    def step(self, G, dt):
        if self.wait > 0:
            self.wait -= dt
            return
        sp = 11.0 if self.eyes else (3.4 if self.fright > 0 else G.espeed)
        if self.d == (0, 0):
            self.d = self.choose(G)
            if self.d == (0, 0):
                return
        self.t += sp * dt
        while self.t >= 1:
            self.t -= 1
            self.tx += self.d[0]
            self.ty += self.d[1]
            if self.eyes and (self.tx, self.ty) == HOME:
                self.eyes, self.wait, self.d, self.t = False, 1.0, (0, 0), 0.0
                return
            self.d = self.choose(G)


# ------------------------------------------------------------------ game ----
class Game:
    def __init__(self, screen, audio):
        self.scr, self.audio = screen, audio
        self.rng = random.Random()
        self.f_s = pygame.font.Font(None, 18)
        self.f_m = pygame.font.Font(None, 26)
        self.f_l = pygame.font.Font(None, 52)
        self.bg = pygame.Surface((W, H))
        for y in range(H):
            u = y / H
            pygame.draw.line(self.bg, (0, 0, 0), (0, y), (W, y))
        self.bokeh = [[self.rng.uniform(0, W), self.rng.uniform(0, H), self.rng.choice((10, 16, 24, 34)),
                       self.rng.uniform(4, 16), self.rng.uniform(0, 6.28)] for _ in range(22)]
        self.state, self.sel, self.sel_x = "menu", 0, 0.0
        self.roll_t = 0.0
        self.time, self.hi, self.score = 0.0, 0, 0
        self.parts, self.pops = [], []
        self.running = True

    # -- setup
    def new_game(self):
        self.score, self.lives, self.level = 0, 3, 0
        self.next_level()

    def next_level(self):
        self.level += 1
        self.grid = gen_maze(self.rng)
        self.home = bfs(self.grid, HOME)
        self.pal = ((15, 55, 235), (35, 100, 255))
        self.wglow, self.wcore = build_maze_surfs(self.grid, self.pal)
        self.powers = set(CORNERS)
        self.pellets = {(x, y) for y in range(ROWS) for x in range(COLS)
                        if not self.grid[y][x]} - self.powers - {PSPAWN}
        self.espeed = min(7.2, 4.6 + self.level * 0.35)
        self.fright_len = max(2.0, 7.0 - self.level * 0.5)
        self.reset_actors()

    def reset_actors(self):
        self.cat = Cat()
        self.bots = [Bot(k) for k in range(4)]
        self.scatter, self.mode_t, self.combo = True, 5.0, 0
        self.state, self.state_t = "ready", 1.8
        self.chomp_t, self.chomp_i = 0.0, 0

    # -- input
    def key(self, k):
        if self.state == "rollcall":
            if k in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.state = "menu"
            return
        if self.state == "menu":
            if k == pygame.K_r:
                self.state, self.roll_t = "rollcall", 0.0
                self.audio.play("roll")
                return
            if k in (pygame.K_LEFT, pygame.K_a):
                self.sel = (self.sel - 1) % 3
                self.audio.play("nav")
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self.sel = (self.sel + 1) % 3
                self.audio.play("nav")
            elif k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                self.audio.play("ok")
                if self.sel == 0:
                    self.new_game()
                elif self.sel == 1:
                    self.audio.toggle_music()
                else:
                    self.running = False
            elif k == pygame.K_ESCAPE:
                self.running = False
            return
        if k == pygame.K_ESCAPE:
            self.state = "menu"
        elif k == pygame.K_m:
            self.audio.toggle_music()
        elif self.state == "over":
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = "menu"
        elif k == pygame.K_p and self.state in ("play", "pause"):
            self.state = "pause" if self.state == "play" else "play"
        else:
            d = {pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0),
                 pygame.K_UP: (0, -1), pygame.K_w: (0, -1), pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1)}.get(k)
            if d:
                self.cat.want = d

    # -- logic
    def burst(self, pos, col, n=6, sp=40):
        for _ in range(n):
            a = self.rng.uniform(0, 6.28)
            v = self.rng.uniform(sp * 0.3, sp)
            self.parts.append([pos[0], pos[1], math.cos(a) * v, math.sin(a) * v, 0.5, col])

    def update(self, dt):
        self.time += dt
        if self.state == "rollcall":
            self.roll_t += dt
        for b in self.bokeh:
            b[1] -= b[3] * dt
            b[0] += math.sin(self.time * 0.3 + b[4]) * 4 * dt
            if b[1] < -40:
                b[1], b[0] = H + 40, self.rng.uniform(0, W)
        self.sel_x += (self.sel - self.sel_x) * min(1, dt * 12)
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        for p in self.pops:
            p[1] -= 14 * dt
            p[3] -= dt
        self.pops = [p for p in self.pops if p[3] > 0]
        if self.state in ("ready", "dying", "clear"):
            self.state_t -= dt
            if self.state_t <= 0:
                if self.state == "ready":
                    self.state = "play"
                elif self.state == "clear":
                    self.next_level()
                else:
                    self.lives -= 1
                    if self.lives <= 0:
                        self.state = "over"
                        self.hi = max(self.hi, self.score)
                    else:
                        self.reset_actors()
            return
        if self.state != "play":
            return
        self.mode_t -= dt
        if self.mode_t <= 0:
            self.scatter = not self.scatter
            self.mode_t = 5.0 if self.scatter else 18.0
        cat = self.cat
        cat.step(self.grid, dt, 7.0)
        cx, cy = cat.pos()
        tile = (int((cx - OX) // T), int((cy - OY) // T))
        self.chomp_t -= dt
        if tile in self.pellets:
            self.pellets.discard(tile)
            self.score += 10
            if self.chomp_t <= 0:
                self.audio.play("c%d" % self.chomp_i)
                self.chomp_i ^= 1
                self.chomp_t = 0.11
            self.burst(tc(*tile), (255, 240, 200), 3, 30)
        elif tile in self.powers:
            self.powers.discard(tile)
            self.score += 50
            self.combo = 0
            self.audio.play("pow")
            self.burst(tc(*tile), (120, 255, 240), 16, 90)
            for b in self.bots:
                if not b.eyes:
                    b.fright = self.fright_len
                    if b.wait <= 0:
                        b.reverse()
        for b in self.bots:
            if b.fright > 0:
                b.fright -= dt
            b.step(self, dt)
            bx, by = b.pos()
            if b.eyes or (cx - bx) ** 2 + (cy - by) ** 2 > 100:
                continue
            if b.fright > 0:
                b.eyes, b.fright = True, 0.0
                self.combo += 1
                pts = 100 * 2 ** self.combo
                self.score += pts
                self.pops.append([bx, by, str(pts), 0.9])
                self.audio.play("eat")
                self.burst((bx, by), b.col, 18, 110)
            else:
                self.state, self.state_t = "dying", 1.3
                self.audio.play("die")
                self.burst((cx, cy), (255, 180, 80), 30, 130)
                return
        self.hi = max(self.hi, self.score)
        if not self.pellets and not self.powers:
            self.state, self.state_t = "clear", 2.0
            self.audio.play("win")

    # -- drawing
    def text(self, s, font, col, pos, anchor="topleft"):
        img = font.render(s, True, col)
        r = img.get_rect(**{anchor: pos})
        self.scr.blit(img, r)
        return r

    def draw_bg(self):
        self.scr.blit(self.bg, (0, 0))
        # Animated studio-like starfield and subtle vignette.
        for x, y, r, _, ph in self.bokeh:
            k = 0.35 + 0.65 * abs(math.sin(self.time * .6 + ph))
            glow(self.scr, (int(x), int(y)), max(5, r//2), (22, 38, 95), k*.35)
        pygame.draw.rect(self.scr, (17, 34, 90), (5, 5, W-10, H-10), 1, border_radius=16)
        

    def draw_menu(self):
        s, t = self.scr, self.time
        self.draw_bg()
        self.text(time.strftime("%H:%M"), self.f_m, (220, 230, 255), (W - 16, 12), "topright")
        draw_cat(s, 26, 24, (1, 0), t, 8)
        self.text("AC KONDO SOFTWARE", self.f_s, (170, 185, 230), (42, 18))
        self.text("PAC-MAN", self.f_l, (255, 255, 255), (W // 2, 78), "center")
        self.text("AC'S PAC-MAN 0.1.1a NEON EDITION", self.f_m, (120, 200, 255), (W // 2, 108), "center")
        labels = ("PLAY", "SFX: " + ("ON" if self.audio.music_on else "OFF"), "QUIT")
        for i, lab in enumerate(labels):
            f = max(0.0, 1 - abs(i - self.sel_x))
            w, h = int(96 + 28 * f), int(96 + 28 * f)
            cx = int(W // 2 + (i - self.sel_x) * 140)
            cy = 210
            r = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
            if f > 0.05:
                glow(s, (cx, cy), 110, (20, 50, 140), f)
            card = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(card, (255, 255, 255, int(22 + 40 * f)), (0, 0, w, h), border_radius=16)
            s.blit(card, r)
            pygame.draw.rect(s, (int(90 + 165 * f),) * 2 + (255,), r, 2, border_radius=16)
            if i == 0:
                draw_cat(s, cx, cy + 4, (1, 0), t, int(18 + 6 * f))
            elif i == 1:
                c = (140, 230, 255) if self.audio.music_on else (90, 100, 130)
                for k in range(5):
                    bh = int((10 + 14 * abs(math.sin(t * 4 + k * 1.3))) * (1 if self.audio.music_on else 0.3)) + 3
                    pygame.draw.rect(s, c, (cx - 22 + k * 10, cy + 14 - bh, 6, bh), border_radius=2)
            else:
                pygame.draw.circle(s, (255, 110, 130), (cx, cy), 18, 3)
                pygame.draw.line(s, (255, 110, 130), (cx, cy - 22), (cx, cy - 4), 3)
            col = tuple(int(140 + 115 * f) for _ in range(3))
            self.text(lab, self.f_m if f > 0.5 else self.f_s, col, (cx, r.bottom + 16), "center")
        self.text("HI  %06d" % self.hi, self.f_s, (170, 185, 230), (W // 2, 330), "center")
        self.text("R  GHOST ROLL CALL", self.f_s, (255, 206, 85), (W//2, 353), "center")
        self.text("<  >  select      ENTER  confirm      ESC  quit", self.f_s, (120, 135, 180), (W // 2, H - 18), "center")

    def draw_rollcall(self):
        self.draw_bg()
        self.text("GHOST ROLL CALL", self.f_l, (255, 224, 65), (W//2, 53), "center")
        self.text("MEET THE MAZE CREW", self.f_s, (145, 200, 255), (W//2, 88), "center")
        for i, name in enumerate(GHOST_NAMES):
            cx = 92 + i * 138
            y = 183 + int(8 * math.sin(self.roll_t*3 + i))
            glow(self.scr, (cx, y), 55, tuple(c//4 for c in BOT_COLS[i]), .8)
            draw_bot(self.scr, cx, y, BOT_COLS[i], (1, 0), self.time, "normal")
            self.text(name, self.f_m, BOT_COLS[i], (cx, 235), "center")
            self.text(("SHADOW", "SPEEDY", "BASHFUL", "POKEY")[i], self.f_s,
                      (210, 225, 255), (cx, 260), "center")
        self.text("ESC / ENTER  BACK TO MENU", self.f_s, (160, 195, 255), (W//2, 352), "center")

    def draw_game(self):
        s, t = self.scr, self.time
        self.draw_bg()
        
        s.blit(self.wglow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        s.blit(self.wcore, (0, 0))
        for p in self.pellets:
            pygame.draw.circle(s, (255, 236, 200), tc(*p), 2)
        pr = 4 + int(1.5 * math.sin(t * 6) + 1.5)
        for p in self.powers:
            c = tc(*p)
            
            pygame.draw.circle(s, (255, 235, 190), c, pr)
        for x, y, _, _, life, col in self.parts:
            k = life / 0.5
            pygame.draw.circle(s, tuple(int(c * k) for c in col), (int(x), int(y)), 1 + int(k * 1.5))
        cx, cy = self.cat.pos()
        for b in self.bots:
            bx, by = b.pos()
            look = (int((cx > bx + 4)) - int((cx < bx - 4)), int((cy > by + 4)) - int((cy < by - 4)))
            mode = "eyes" if b.eyes else ("normal" if b.fright <= 0 else
                                          ("flash" if b.fright < 2 and int(b.fright * 6) % 2 else "fright"))
            draw_bot(s, bx, by, b.col, look, t, mode)
        if self.state != "dying":
            draw_cat(s, cx, cy, self.cat.face, t)
        elif self.state_t > 0.3:
            draw_cat(s, cx, cy, (0, 0), t * 4, max(1, int(7 * (self.state_t - 0.3))))
        for x, y, txt, life in self.pops:
            self.text(txt, self.f_s, (150, 255, 240), (x, y), "center")
        self.text("SCORE  %06d" % self.score, self.f_m, (255, 255, 255), (OX, 8))
        self.text("HI  %06d" % self.hi, self.f_s, (170, 185, 230), (W // 2 + 30, 12))
        self.text("LEVEL %d" % self.level, self.f_m, self.pal[1], (OX + COLS * T, 8), "topright")
        for i in range(self.lives - 1):
            draw_cat(s, OX + 10 + i * 20, H - 15, (1, 0), 0.5, 6)
        self.text("ARROWS/WASD move   P pause   M SFX   ESC menu", self.f_s, (120, 135, 180), (OX + COLS * T, H - 22), "topright")
        msg = {"ready": "READY!", "pause": "PAUSED", "clear": "LEVEL CLEAR", "over": "GAME OVER"}.get(self.state)
        if msg:
            if self.state in ("pause", "over"):
                dim = pygame.Surface((W, H), pygame.SRCALPHA)
                dim.fill((0, 0, 20, 150))
                s.blit(dim, (0, 0))
            
            self.text(msg, self.f_l, (255, 255, 255), (W // 2, H // 2), "center")
            if self.state == "over":
                self.text("ENTER  back to menu", self.f_s, (170, 185, 230), (W // 2, H // 2 + 34), "center")

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "rollcall":
            self.draw_rollcall()
        else:
            self.draw_game()


def main(max_frames=None, script=None):
    audio = Audio()
    pygame.init()
    window = pygame.display.set_mode((DISPLAY_W, DISPLAY_H), pygame.RESIZABLE)
    screen = pygame.Surface((W, H)).convert()
    pygame.display.set_caption("AC's Pac-Man 0.1.1a | Neon HD Edition")
    clock = pygame.time.Clock()
    g = Game(screen, audio)
    g.draw_bg()
    g.text("LOADING", g.f_m, (200, 215, 255), (W // 2, H // 2), "center")
    pygame.event.pump()
    audio.build()
    clock.tick()
    frame = 0
    while g.running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.VIDEORESIZE:
                window = pygame.display.set_mode(e.size, pygame.RESIZABLE)
            if e.type == pygame.QUIT:
                g.running = False
            elif e.type == pygame.KEYDOWN:
                g.key(e.key)
        if script:
            script(g, frame)
        g.update(dt)
        audio.sync(g.state)
        g.draw()
        # Widescreen presentation with aspect-correct 3:2 gameplay viewport.
        ww, wh = window.get_size()
        scale = min(ww / W, wh / H)
        rw, rh = max(1, int(W * scale)), max(1, int(H * scale))
        ox, oy = (ww-rw)//2, (wh-rh)//2
        window.fill((2, 3, 15))
        frame_hd = pygame.transform.smoothscale(screen, (rw, rh))
        window.blit(frame_hd, (ox, oy))
        pygame.display.flip()
        frame += 1
        if max_frames and frame >= max_frames:
            break
    pygame.quit()
    return g


if __name__ == "__main__":
    main()
    sys.exit(0)
